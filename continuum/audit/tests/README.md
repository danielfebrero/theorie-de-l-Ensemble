# Tests de conformité

`test_conformance.py` expose à `unittest discover` la suite source conservée un
niveau plus haut, à côté des checkers qu’elle exerce.

```bash
python3 -m unittest discover -s continuum/audit/tests -v
```
