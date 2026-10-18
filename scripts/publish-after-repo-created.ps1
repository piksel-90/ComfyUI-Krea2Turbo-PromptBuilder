# Run after creating an EMPTY repository called ComfyUI-Krea2Turbo-PromptBuilder
# under the piksel-90 GitHub account. Requires git + GitHub authentication.
$ErrorActionPreference = 'Stop'
git remote add origin https://github.com/piksel-90/ComfyUI-Krea2Turbo-PromptBuilder.git
git push -u origin main
git push origin v0.1.0
