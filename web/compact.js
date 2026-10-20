// Optional ComfyUI canvas UI enhancement. No external requests, dependencies, or model changes.
import { app } from "../../scripts/app.js";

const NODE_NAMES = new Set(["Krea2TurboPromptBuilderV01", "Krea2TurboPromptBuilderV018"]);
const PANEL_NAME = "⚙ Settings panel";
const PANELS = ["Basic", "Advanced", "Diagnostics", "All"];
// These three fields are visible in Basic, Advanced, Diagnostics and All.
// Legacy V01 retains its original two field names for saved-workflow safety.
const ALWAYS = new Set(["original_prompt", "target", "extra_instruction", "source_prompt", "user_goal"]);
const BASIC = new Set(["model_gguf", "mode"]);
const ADVANCED = new Set([
  "mmproj_gguf", "llama_cli_path", "image_index", "max_image_side", "gpu_layers",
  "vision_gpu", "context_size", "max_tokens", "batch_size", "timeout_seconds",
  "execution_device", "output_mode", "reasoning", "model_path_override",
  "mmproj_path_override", "memory_handoff",
]);
const DIAGNOSTICS = new Set([
  "save_diagnostics", "commit_headroom_gib", "scene_contract",
  "required_exact_phrases", "forbidden_exact_phrases", "memory_handoff",
]);

function setHidden(widget, hidden) {
  if (!widget || widget.name === PANEL_NAME) return;
  if (!widget.__kreaOriginal) {
    widget.__kreaOriginal = {
      type: widget.type,
      computeSize: widget.computeSize,
      hidden: widget.hidden,
      optionsHidden: widget.options?.hidden,
      display: widget.element?.style?.display,
      inputDisplay: widget.inputEl?.style?.display,
    };
  }
  const old = widget.__kreaOriginal;
  widget.options = widget.options || {};
  widget.hidden = hidden ? true : old.hidden;
  widget.options.hidden = hidden ? true : old.optionsHidden;
  widget.type = hidden ? "krea-collapsed-widget" : old.type;
  widget.computeSize = hidden ? () => [0, -4] : old.computeSize;
  if (widget.element?.style) widget.element.style.display = hidden ? "none" : (old.display ?? "");
  if (widget.inputEl?.style) widget.inputEl.style.display = hidden ? "none" : (old.inputDisplay ?? "");
}

function isConnectedWidget(node, name) {
  // Keep a converted-to-input widget available. Hiding linked inputs can break old workflows.
  return !!node.inputs?.some(input =>
    input?.link != null && (input?.widget?.name === name || input?.name === name));
}

function refresh(node) {
  if (!node.widgets?.length) return;
  const panel = PANELS.includes(node.properties?.kreaUiPanel)
    ? node.properties.kreaUiPanel : "Basic";
  for (const widget of node.widgets) {
    if (widget.name === PANEL_NAME) {
      widget.value = panel;
      continue;
    }
    const name = widget.name;
    const visible = panel === "All" || ALWAYS.has(name) || BASIC.has(name) ||
      (panel === "Advanced" && ADVANCED.has(name)) ||
      (panel === "Diagnostics" && DIAGNOSTICS.has(name)) ||
      (!ADVANCED.has(name) && !DIAGNOSTICS.has(name) && !BASIC.has(name));
    setHidden(widget, !visible && !isConnectedWidget(node, name));
  }
  try {
    const measured = node.computeSize?.();
    if (Array.isArray(measured) && Number.isFinite(measured[1])) {
      node.setSize?.([Math.max(node.size?.[0] || 340, 340), Math.max(measured[1], 120)]);
    }
  } catch (_) {
    // Never interfere with normal ComfyUI workflow execution on frontend differences.
  }
  node.setDirtyCanvas?.(true, true);
}

function initialize(node) {
  if (node.__kreaPanelInstalled || !node.addWidget) return;
  node.__kreaPanelInstalled = true;
  node.properties = node.properties || {};
  const selected = PANELS.includes(node.properties.kreaUiPanel) ? node.properties.kreaUiPanel : "Basic";
  node.properties.kreaUiPanel = selected;
  // Append to avoid shifting the indexes of existing widgets_values in saved workflows.
  const widget = node.addWidget("combo", PANEL_NAME, selected, value => {
    node.properties.kreaUiPanel = PANELS.includes(value) ? value : "Basic";
    refresh(node);
  }, { values: PANELS, serialize: false });
  widget.serializeValue = () => undefined;
  refresh(node);
}

app.registerExtension({
  name: "krea.prompt_builder.compact_ui",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (!NODE_NAMES.has(nodeData.name)) return;
    const origCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function (...args) {
      const result = origCreated?.apply(this, args);
      queueMicrotask(() => initialize(this));
      return result;
    };
    const origConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function (...args) {
      const result = origConfigure?.apply(this, args);
      queueMicrotask(() => { initialize(this); refresh(this); });
      return result;
    };
  },
});
