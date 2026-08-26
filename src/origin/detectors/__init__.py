"""Similarity detectors. Section 7 of the specification.

The package exposes only the shared contract (`base`) and an empty registry
(`registry`). No detector registers itself here - wiring detectors into the
registry belongs to the task that builds the pipeline. Importing a concrete
detector goes straight through its module, for example
`from origin.detectors import fingerprint`.
"""
