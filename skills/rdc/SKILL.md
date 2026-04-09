---
name: renderdoc-cli
description: AI-friendly command-line interface for RenderDoc .rdc capture analysis. Use when user needs to analyze graphics debugging captures (.rdc files) through terminal commands. Trigger phrases include: "renderdoc-cli command", "RenderDoc CLI", "analyze .rdc file", "check draw calls", "inspect pipeline state", "shader debugging", "compare render targets", or any request involving RenderDoc capture file analysis that would benefit from terminal-based workflows rather than MCP tool calls.
---

# RenderDoc CLI (renderdoc-cli)

AI-friendly command-line interface for analyzing RenderDoc `.rdc` capture files.

**Prerequisites:**
- RenderDoc 1.20+ running with renderdoc_toolset_bridge extension loaded
- `renderdoc-cli` command installed (see README for installation)

## Quick Workflow

```bash
# 1. Open a capture
renderdoc-cli open D:\captures\frame.rdc

# 2. Quick overview
renderdoc-cli info
renderdoc-cli summary

# 3. Find relevant draw calls
renderdoc-cli draws --marker "ShadowPass"
renderdoc-cli draws -p unity_game_rendering

# 4. Inspect specific event
renderdoc-cli draw-detail 42
renderdoc-cli pipeline 42

# 5. Debug shader
renderdoc-cli shader-source 42 pixel > main.hlsl
# Edit the file...
renderdoc-cli edit-shader 42 pixel main.hlsl

# 6. Compare render targets
renderdoc-cli rt-diff 42 --compare 40 -o diff.png
```

## Command Reference

### Capture Operations
| Command | Description |
|---------|-------------|
| `renderdoc-cli status` | Check if capture is loaded |
| `renderdoc-cli info` | Capture details (API, driver, GPU, stats) |
| `renderdoc-cli list-captures <dir>` | List all .rdc files in directory |
| `renderdoc-cli open <path>` | Open a capture file |

### Draw Call Analysis
| Command | Description |
|---------|-------------|
| `renderdoc-cli draws [--marker X] [-p preset]` | Get draw calls with filtering |
| `renderdoc-cli summary` | Frame statistics overview |
| `renderdoc-cli draw-detail <id>` | Single draw call details |
| `renderdoc-cli timings [-p preset]` | GPU timing information |

### Pipeline State
| Command | Description |
|---------|-------------|
| `renderdoc-cli pipeline <id>` | Complete pipeline state |
| `renderdoc-cli diff <base> <target>` | Compare pipeline states |
| `renderdoc-cli replay <id>` | Replay to specific event |

### Shader Operations
| Command | Description |
|---------|-------------|
| `renderdoc-cli shader-info <id> <stage>` | Shader metadata |
| `renderdoc-cli shader-source <id> <stage>` | Export shader source code |
| `renderdoc-cli edit-shader <id> <stage> <file>` | Replace shader (use `-` for stdin) |
| `renderdoc-cli revert-shader <id> <stage>` | Restore original shader |

### Resource Queries
| Command | Description |
|---------|-------------|
| `renderdoc-cli textures` | List all textures |
| `renderdoc-cli texture-thumb <id>` | Texture thumbnail PNG |
| `renderdoc-cli texture-save <id> -o out.png` | Full-resolution texture PNG |
| `renderdoc-cli rt-thumb <id>` | Render target thumbnail |
| `renderdoc-cli rt-diff <id> [--compare <id>]` | Pixel-level render target diff |

### Session Management
| Command | Description |
|---------|-------------|
| `renderdoc-cli sessions` | List active RenderDoc sessions |
| `renderdoc-cli use <session_id>` | Switch default session |
| `renderdoc-cli ping` | Test bridge latency |

## Output Format

```bash
renderdoc-cli info -f json        # JSON format (default)
renderdoc-cli draws -f tsv        # TSV format for grep/awk
renderdoc-cli pipeline 42 -o state.json  # Write to file
```

## When to Use This vs MCP Tools

| Aspect | renderdoc-cli | MCP Tools |
|--------|---------|-----------|
| **Usage** | Terminal commands | AI assistant tools |
| **Automation** | Shell scripting | Natural language |
| **Output** | JSON/TSV files | Structured data in conversation |
| **Best for** | Batch processing, manual debugging | Interactive exploration, analysis |

Use **renderdoc-cli** when:
- Writing shell scripts for batch processing
- Preferring terminal-based workflows
- Need to pipe output to other tools
- Quick ad-hoc checks without AI assistance

Use **MCP tools** (renderdoc-tool-set server) when:
- Exploring captures interactively with AI
- Need multi-step analysis
- Generating reports or explanations
- Natural language queries

## Filtering Presets

Built-in presets for common scenarios:
- `unity_game_rendering` - Focus on Camera.Render, exclude Unity editor UI
- `unity_ui_rendering` - UI rendering pass
- `unity_shadow_debug` - Shadow pass only
- `dispatch_only` - Compute dispatch actions only

Example:
```bash
renderdoc-cli draws -p unity_game_rendering
renderdoc-cli timings -p unity_shadow_debug
```
