---
bundle:
  name: the-usual
  version: 3.0.0
  description: '"The usual" — a rigorous, self-contained development workflow: plan, validate load-bearing assumptions, independent cross-model review loops, subagent-driven execution, and a plain-language recap'

includes:
  - bundle: git+https://github.com/microsoft/amplifier-foundation@93615d9847ce40313cc0d60583cb886de4337f9e
  - bundle: git+https://github.com/microsoft/amplifier-bundle-recipes@b6ee26d3a3d59a99f75c362855be7a89d7762fb0
  - bundle: the-usual:behaviors/the-usual
---

# The Usual

@foundation:context/shared/common-system-base.md
