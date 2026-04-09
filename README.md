# RenderDoc Tool Set

## 1. 项目概述
RenderDoc Tool Set 是一个专为 AI 助手和自动化脚本设计的 RenderDoc 捕获文件（`.rdc`）分析工具集。它通过提供 MCP (Model Context Protocol) 服务和强大的命令行接口（CLI），使得 AI 模型和开发者能够以编程和自然语言的方式深入分析图形渲染过程。

## 2. 功能特性
- **双重接口支持**：
  - **MCP Server**：无缝集成到支持 MCP 的 AI 助手（如 Claude、Cursor 等），允许 AI 直接读取和分析渲染数据。
- **CLI 工具 (`renderdoc-cli`)**：提供丰富的命令行指令，适合终端工作流和自动化脚本批处理。
- **全面的渲染分析能力**：
  - **捕获管理**：加载、查看状态和获取捕获文件的详细信息。
  - **Draw Call 分析**：获取绘制调用列表、帧统计摘要、详细信息及 GPU 耗时。
  - **管线状态 (Pipeline State)**：检查特定事件的完整管线状态，支持不同事件间的状态对比（Diff）。
  - **着色器调试 (Shader)**：查看着色器元数据、导出源码、甚至支持动态编辑和还原着色器代码。
  - **资源查询**：读取 Buffer 内容、纹理信息、导出纹理/渲染目标（Render Target）的缩略图或原图，支持像素级差异对比。
- **多会话支持**：支持同时连接和管理多个 RenderDoc 实例。
- **预设过滤**：内置多种过滤预设（如 Unity 游戏渲染、UI 渲染等），快速定位关键 Draw Call。

## 3. 快速开始

### 环境要求
- Python 3.10 或更高版本
- [uv](https://docs.astral.sh/uv/) 包管理器
- RenderDoc 1.20 或更高版本

### 安装步骤

#### Windows 快捷安装
在 PowerShell 中运行提供的安装脚本：
```powershell
powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/DreamFields/renderdoc-tool-set/master/install.ps1 | iex"
```

#### 手动安装
1. 克隆仓库并进入目录：
   ```bash
   git clone https://github.com/DreamFields/renderdoc-tool-set.git
   cd renderdoc-tool-set
   ```
2. 同步 Python 环境并安装 RenderDoc 扩展：
   ```bash
   uv sync
   python scripts/install_extension.py sync
   ```
3. 将 CLI 和 MCP Server 安装到全局环境：
   ```bash
   uv tool install .
   ```

### 启用扩展
安装完成后，请按照以下步骤在 RenderDoc 中启用扩展：
1. 重启 RenderDoc。
2. 导航至菜单栏：`Tools` > `Manage Extensions`。
3. 找到并勾选 `RenderDoc renderdoc_toolset_bridge`。

## 4. 使用说明

### 作为 MCP Server 使用
在您的 AI 助手（如 Claude Desktop 或 Cursor）的 MCP 配置文件中，添加以下配置：
```json
{
  "mcpServers": {
    "renderdoc": {
      "command": "renderdoc_toolset"
    }
  }
}
```

### 作为 CLI 工具使用 (`renderdoc-cli`)
安装后，您可以在终端中直接使用 `renderdoc-cli` 命令。

**常用命令示例：**
```bash
# 打开一个捕获文件
renderdoc-cli open D:\captures\frame.rdc

# 查看帧统计摘要
renderdoc-cli summary

# 查找特定的 Draw Call（支持预设过滤）
renderdoc-cli draws -p unity_game_rendering

# 查看特定事件的管线状态
renderdoc-cli pipeline 42

# 导出特定事件的像素着色器源码
renderdoc-cli shader-source 42 pixel > main.hlsl

# 对比两个事件的渲染目标差异
renderdoc-cli rt-diff 42 --compare 40 -o diff.png
```
使用 `renderdoc-cli --help` 查看所有可用命令和详细参数。

## 5. 贡献指南
我们欢迎任何形式的贡献！如果您想为项目做出贡献，请遵循以下步骤：
1. Fork 本仓库。
2. 创建您的特性分支 (`git checkout -b feature/AmazingFeature`)。
3. 提交您的更改 (`git commit -m 'Add some AmazingFeature'`)。
4. 推送到分支 (`git push origin feature/AmazingFeature`)。
5. 开启一个 Pull Request。

如果您发现了 Bug 或有新的功能建议，请在 GitHub Issues 中提交。

## 6. 许可证信息
本项目采用 [MIT 许可证](LICENSE) 开源。详情请参阅 `LICENSE` 文件。

## 7. 联系方式
- **项目主页**: [https://github.com/DreamFields/renderdoc-tool-set](https://github.com/DreamFields/renderdoc-tool-set)
- **问题反馈**: 请通过 GitHub Issues 提交您遇到的问题或建议。