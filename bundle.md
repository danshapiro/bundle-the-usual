---
bundle:
  name: the-usual
  version: 1.0.0
  description: '"The usual" — a rigorous, self-contained development workflow: plan, validate load-bearing assumptions, independent cross-model review loops, subagent-driven execution, and a plain-language recap'

includes:
  - bundle: git+https://github.com/microsoft/amplifier-foundation@main
  - bundle: git+https://github.com/microsoft/amplifier-bundle-recipes@main
  - bundle: the-usual:behaviors/the-usual
---

# The Usual

@foundation:context/shared/common-system-base.md
