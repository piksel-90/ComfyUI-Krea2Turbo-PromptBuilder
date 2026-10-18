#!/usr/bin/env bash
set -euo pipefail
# Run after creating the EMPTY GitHub repository under piksel-90.
git remote add origin https://github.com/piksel-90/ComfyUI-Krea2Turbo-PromptBuilder.git
git push -u origin main
git push origin v0.1.0
