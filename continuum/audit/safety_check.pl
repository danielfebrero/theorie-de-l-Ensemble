#!/usr/bin/env perl
# Vérification structurelle version-agnostique du noyau de sûreté M3C3.
# Usage: perl continuum/audit/safety_check.pl [--format text|json] [master.yaml]
use strict;
use warnings;
use utf8;
use Getopt::Long qw(GetOptions);
use JSON::PP qw(encode_json);

my $format = "text";
GetOptions("format=s" => \$format) or die "usage: $0 [--format text|json] [master.yaml]\n";
die "--format must be text or json\n" unless $format eq "text" || $format eq "json";

my $path = $ARGV[0] // "master.yaml";
open my $fh, "<:encoding(UTF-8)", $path or die "open $path: $!\n";
local $/;
my $yaml = <$fh>;
close $fh;

my @failures;
my @checks;

# PyYAML écrase silencieusement les doublons par défaut. Le loader partagé les
# refuse avant que les regex structurelles ne puissent certifier la mauvaise
# occurrence.
my $strict_checker = $0;
$strict_checker =~ s/safety_check\.pl$/yaml_strict.py/;
my $strict_output = "";
if (open my $strict_fh, "-|", "python3", $strict_checker, "--format", "json", $path) {
  local $/;
  $strict_output = <$strict_fh> // "";
  close $strict_fh;
  my $strict_exit = $? >> 8;
  if ($strict_exit == 0) {
    push @checks, "strict_yaml";
  } else {
    push @failures, { code => "strict_yaml", detail => $strict_output || "duplicate/invalid YAML" };
  }
} else {
  push @failures, { code => "strict_yaml", detail => "cannot execute $strict_checker" };
}

sub need {
  my ($code, $regex, $message) = @_;
  if ($yaml =~ $regex) {
    push @checks, $code;
  } else {
    push @failures, { code => $code, detail => $message };
  }
}

my ($version) = $yaml =~ /^\s{2}version:\s*["']?([0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?)["']?\s*$/m;
if (defined $version) {
  push @checks, "semantic_version";
} else {
  $version = "unknown";
  push @failures, { code => "semantic_version", detail => "master_document.version must be semantic" };
}

my ($release_major) = $yaml =~ /^\s{4}major:\s*([0-9]+)\s*$/m;
if ($version ne "unknown" && defined $release_major && $version =~ /^([0-9]+)/ && $release_major == $1) {
  push @checks, "release_major_matches_version";
} else {
  push @failures, {
    code => "release_major_matches_version",
    detail => "release.major must match the semantic-version major"
  };
}

need("status_present", qr/^\s{2}status:\s*["']?[a-z][a-z0-9_-]*["']?\s*$/mi,
  "master_document.status missing or malformed");
need("activation_eligible", qr/eligible_when_known|eligible_for_activation/,
  "activation must retain eligible_when_known");
need("known_implies_eligible", qr/known\(M3C3\).*eligible|eligible_for_activation/s,
  "predicate known(M3C3) => eligible missing");
need("not_auto_on", qr/not_auto_on:\s*true/,
  "activation must remain non-automatic");

for my $type (qw(B F(B) M(F) C(M) P(C) L(P))) {
  need("layer_type_$type", qr/\Q$type\E/, "missing layer type $type");
}

need("write_rule", qr/write\(i\s*→\s*j\)|write\(i → j\)/, "write_rule missing");
need("recovery_path", qr/RecoveryPath/, "RecoveryPath missing from write_rule");
need("capability_semantics", qr/capability_token|Cap\(i/, "capability missing from formal semantics");

need("transition_capability", qr/Capability\(x_t\)/, "Capability transition guard missing");
need("transition_health", qr/Health_F4/, "Health_F4 transition guard missing");
need("transition_ruin", qr/¬Ruin|\\neg Ruin|Ruin\(x/, "Ruin transition guard missing");
need("transition_evidence", qr/Evidence\(x_t\)\s*(?:≥|>=)/, "Evidence >= tau guard missing");
need("transition_failure_path", qr/Resolve.*Recover.*Kill|Resolve ∨ Recover ∨ Kill/s,
  "failure path Resolve|Recover|Kill missing");

for my $id (qw(S1_health_critical S2_cross_layer_cap S3_ruin_irreversible S4_no_upward_write S5_eligible_known)) {
  need("safety_$id", qr/\Q$id\E/, "missing safety id $id");
}
need("proof_status", qr/proved_by_construction/, "proof_status proved_by_construction missing");
need("export_binding", qr/export_binding/, "export_binding missing");
need("lts", qr/labeled_transition_system|alphabet:/, "labeled transition system missing");

# Témoins rapides des bases gelées. Le contrôle exact, exhaustif et typé est
# effectué par superset_check.py contre master.yaml@v1.0.0.
need("frozen_life_weight", qr/life_game_M1C1:\s*0\.25(?:\s|$)/, "life_game weight changed or missing");
need("frozen_utility_weight", qr/utility_expected_value:\s*0\.45(?:\s|$)/,
  "quantifiable utility weight changed or missing");
need("frozen_authorship", qr/author_creator:\s*Dani Bengal/, "authorship lock missing");

my $result = {
  checker => "safety_kernel",
  ok => @failures ? JSON::PP::false : JSON::PP::true,
  path => $path,
  version => $version,
  checks => \@checks,
  failures => \@failures,
};

if ($format eq "json") {
  binmode STDOUT, ":raw";
  print encode_json($result), "\n";
} else {
  binmode STDOUT, ":encoding(UTF-8)";
  if (@failures) {
    print "SAFETY CHECK FAIL ($path, v$version)\n";
    print "  - $_->{code}: $_->{detail}\n" for @failures;
  } else {
    print "SAFETY CHECK OK ($path, v$version) — structural kernel intact\n";
  }
}

exit(@failures ? 1 : 0);
