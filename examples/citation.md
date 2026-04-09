---
title: "VCITE Citation Example — Pandoc Markdown"
vcite-version: "1.0"
---

# The Link Rot Problem

Digital scholarship depends on stable references, but the web's
mutability undermines this assumption. As documented by Zittrain et al.,
[over 70% of the URLs provided in articles published in the Harvard Law
Review did not lead to originally cited
information]{.vcite vcite-id="vcite-d2ba5887"
vcite-hash="sha256:d2ba5887d4456199ce37a7860ce011485519925dc75c3564f50d1ffa1e1dc933"
vcite-relation="supports" vcite-captured-by="author"}
[@zittrain2014perma, p. 4]. This rate of decay accelerates over time.

The Columbia Journalism Review found that [eight major AI search tools
provided incorrect or inaccurate answers to more than 60% of 1,600 test
queries]{.vcite vcite-id="vcite-26c71181"
vcite-hash="sha256:26c71181069e54c4d776f2a03de838c81aab3eff1a64a71ecde920f629367707"
vcite-relation="quantifies" vcite-captured-by="author"}
[@lim2025aisearch], with error rates ranging across tools and query
types.

## Pandoc Usage

Compile with a VCITE Lua filter to produce HTML with embedded JSON-LD:

```bash
pandoc citation.md \
  --lua-filter=vcite.lua \
  --citeproc \
  --bibliography=references.bib \
  -o citation.html
```

The `.vcite` class on bracketed spans triggers the filter. Required
attributes:

| Attribute            | Required | Description                          |
|----------------------|----------|--------------------------------------|
| `vcite-id`           | Yes      | VCITE object identifier              |
| `vcite-hash`         | Yes      | SHA-256 passage fingerprint          |
| `vcite-relation`     | No       | Semantic relation (default: supports)|
| `vcite-captured-by`  | No       | "author" or "model"                  |

The filter emits `<span data-vcite>` elements in HTML output and
injects the corresponding JSON-LD `<script>` blocks into `<head>`.

## References
