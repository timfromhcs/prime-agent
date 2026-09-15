---
name: image_creation
description: Plan image prompts, generate visual artifacts, perform image-to-image editing, and verify outputs via Visual QA.
---

# Image Creation and Editing Skill

Use this skill to create and edit images headlessly using the local diffusion pipeline.

## Rules
1. Plan detailed descriptive prompts including subject, lighting, style, and composition.
2. For editing, use image-to-image with appropriate strength (0.4 to 0.75) to preserve subject structure.
3. Every generated or edited image must be saved in `data/artifacts/` with a SHA-256 record and verified by the Vision QA system.
