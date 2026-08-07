#!/usr/bin/env perl
# safety_check.pl — vérification structurelle du noyau de sûreté M3C3 v1.0
# Usage: perl continuum/audit/safety_check.pl [master.yaml]
# Exit 0 si OK, 1 sinon.
use strict;
use warnings;
use utf8;

my $path = $ARGV[0] // "master.yaml";
open my $fh, "<:encoding(UTF-8)", $path or die "open $path: $!\n";
local $/; my $y = <$fh>; close $fh;

my @fail;

sub need {
  my ($re, $msg) = @_;
  push @fail, $msg unless $y =~ $re;
}

need(qr/version:\s*1\.0\.0/, "version must be 1.0.0");
need(qr/status:\s*production/, "status must be production");
need(qr/eligible_when_known|eligible_for_activation/, "activation eligible_when_known");
need(qr/known\(M3C3\).*eligible|eligible_for_activation/, "predicate known⇒eligible");

# Layer types
for my $t (qw(B F\(B\) M\(F\) C\(M\) P\(C\) L\(P\))) {
  need(qr/\Q$t\E/, "missing layer type $t");
}

# Write rule pieces
need(qr/write\(i\s*→\s*j\)|write\(i → j\)/, "write_rule present");
need(qr/RecoveryPath/, "RecoveryPath in write_rule");
need(qr/capability_token|Cap\(i/, "capability in formal semantics");

# Transition guard
need(qr/Capability\(x_t\)/, "Capability guard");
need(qr/Health_F4/, "Health_F4 guard");
need(qr/¬Ruin|\\\\neg Ruin|Ruin\(x/, "Ruin guard");
need(qr/Evidence\(x_t\)\s*≥|Evidence\(x_t\) >=/, "Evidence≥τ guard");
need(qr/Resolve.*Recover.*Kill|Resolve ∨ Recover ∨ Kill/, "failure path Resolve|Recover|Kill");

# Safety IDs
for my $id (qw(S1_health_critical S2_cross_layer_cap S3_ruin_irreversible S4_no_upward_write S5_eligible_known)) {
  need(qr/\Q$id\E/, "missing safety id $id");
}
need(qr/proved_by_construction/, "proof_status proved_by_construction");
need(qr/export_binding/, "export_binding present");
need(qr/labeled_transition_system|alphabet:/, "LTS alphabet");

# Frozen bases still present
need(qr/life_game_M1C1:\s*0\.25/, "hierarchy weight life_game");
need(qr/utility_expected_value:\s*0\.45/, "quantifiable utility stack");
need(qr/author_creator:\s*Dani Bengal/, "authorship lock");

if (@fail) {
  print "SAFETY CHECK FAIL ($path)\n";
  print "  - $_\n" for @fail;
  exit 1;
}
print "SAFETY CHECK OK ($path) — v1.0 structural kernel intact\n";
exit 0;
