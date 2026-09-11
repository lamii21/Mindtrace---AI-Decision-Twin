# Notebooks

Exploration and calibration studies only - the MCDA prototype behind
`docs/spec/05-mcda-mathematics.md`, confidence-weight sensitivity studies, and
similar. **Nothing under `backend/src/mindtrace/` imports a notebook**, and a
notebook may freely `import mindtrace.engines` (once M2 adds it) to prototype
against the real, tested code.

CI strips output cells (`nbstripout --verify`) so a committed notebook carries
no stale execution state or embedded binary blobs.

Nothing lives here yet - the first entry arrives with M2 (`mcda_prototype.ipynb`).
