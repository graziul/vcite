# Contributing to VCITE

Thank you for your interest in improving VCITE. This document explains how
to propose changes, add implementations, and report bugs.

## Proposing spec changes

1. Open a GitHub issue with the tag `spec-change`.
2. Include: which section you want to change, what the change is, and why
   it is needed.
3. Breaking changes to the hash algorithm (Section 5) require a major
   version bump. Non-breaking additions to the data model or new
   serialization formats can go in a minor version.
4. All spec changes are reviewed by the project maintainer before merging.

## Adding an implementation

1. Create a directory under `implementations/your-language/`.
2. Your implementation MUST pass all four mandatory test vectors (SV1--SV4)
   in `test-suite/vectors.yaml`. It SHOULD pass all 23 vectors.
3. Include a README with install and usage instructions.
4. Include a test runner that loads `test-suite/vectors.yaml` and reports
   pass/fail for each vector.
5. Open a pull request. The PR description should state which vectors pass
   and on which platform(s) the implementation was tested.

## Reporting bugs

**Hash mismatch**: include your input (`text_exact`, `text_before`,
`text_after`), expected output, actual output, language, runtime version,
and platform (OS, architecture).

**Schema issue**: include the JSON object and the validation error message.

**Spec ambiguity**: open an issue with the tag `spec-clarification`. Quote
the ambiguous passage and describe the two plausible interpretations.

## Proposing test vectors

Open a GitHub issue with the tag `test-vector`. Include: a description of
the edge case, all three input fields, the expected hash (computed by the
reference implementation), and which category the vector belongs to.

## Style

- Keep issues and PRs focused. One issue per topic.
- Use clear, specific titles.
- Reference spec sections by number (e.g., "Section 5.1").

## Code of conduct

We follow the [Contributor Covenant v2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
