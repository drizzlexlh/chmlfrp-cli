# src/chml/main.py
import typer
from rich import print as rich_print
import importlib.resources
import os
import sys
import httpx
import yaml
import subprocess
import platform
from InquirerPy import inquirer
from typing import List, Optional, Any

app = typer.Typer(help="Frp 客户端配置和运行工具.")

# --- 使用 importlib.resources 获取数据文件路径 ---
def get_resource_path(resource_path: str) -> str:
    """获取包内数据文件的绝对路径."""
    try:
        file_path = importlib.resources.files('chml').joinpath(resource_path)
        return str(file_path)
    except Exception as e:
        rich_print(f"[red]❌ 获取资源文件路径失败: {resource_path}[/red] [yellow]{e}[/yellow]")
        return ""

# --- 定义文件/目录名 (相对路径) ---
CONFIG_FILE_NAME = "config.yaml"
FRP_DIR_NAME = "frp"
FRPC_INI_NAME = "frpc.ini"

# 根据操作系统确定 frpc 可执行文件名
if platform.system() == "Windows":
    FRPC_EXE_NAME = "frpc.exe"
else: # Linux, macOS, etc.
    FRPC_EXE_NAME = "frpc"

# --- 构建完整的绝对路径 (使用 importlib.resources) ---
CONFIG_FILE_PATH = get_resource_path(CONFIG_FILE_NAME)
FRP_DIR_PATH = get_resource_path(FRP_DIR_NAME)
FRPC_INI_PATH = get_resource_path(os.path.join(FRP_DIR_NAME, FRPC_INI_NAME))
FRPC_EXE_PATH = get_resource_path(os.path.join(FRP_DIR_NAME, FRPC_EXE_NAME))

# --- API URLs ---
TUNNEL_URL = "https://cf-v2.uapis.cn/tunnel"
TUNNEL_CONFIG_URL = "https://cf-v2.uapis.cn/tunnel_config"

# --- 自定义异常 ---
class ConfigError(Exception):
    """配置相关的自定义异常。"""
    pass

class APIError(Exception):
    """API 请求相关的自定义异常。"""
    pass

# --- 核心逻辑函数 (全部改为同步 def) ---

# init_config 改为同步函数
def init_config() -> str:
    """初始化配置，如果配置文件不存在则提示用户输入 token。"""
    token = None
    try:
        # 使用绝对路径读取配置文件
        with open(CONFIG_FILE_PATH, "r") as f:
            config_data = yaml.safe_load(f)
            # 检查配置数据是否存在且是字典，并且包含非空 token
            if not isinstance(config_data, dict) or not config_data.get("token"):
                raise ConfigError("Token 不存在或配置文件格式错误")
            token = config_data["token"] # 确保 token 字段存在才获取
            if not token: # 明确区分 token 字段存在但为空的情况
                 raise ConfigError("Token 字段为空")
            rich_print(f"[green]✅ 找到现有配置:[/green] [cyan]{CONFIG_FILE_PATH}[/cyan]")
            return token
    except (FileNotFoundError, ConfigError, yaml.YAMLError) as e:
        # 统一处理文件不存在、格式错误和Token问题
        issue_msg = ""
        if isinstance(e, FileNotFoundError):
            issue_msg = f"未找到配置文件: [cyan]{CONFIG_FILE_PATH}[/cyan]"
        elif isinstance(e, yaml.YAMLError):
             issue_msg = f"配置文件解析失败: {e}"
        elif isinstance(e, ConfigError):
             issue_msg = f"配置错误: {e}"

        rich_print(f"[yellow]⚠️ {issue_msg}，将尝试创建新配置。[/yellow]")

        # 使用 inquirer 进行交互式输入 - 在同步函数中直接调用
        try:
            # 直接调用 execute，因为整个函数是同步的
            token = inquirer.text(message="请输入你的 token:").execute()
            if not token: # 检查用户是否输入了内容
                rich_print("[red]❌ Token 输入不能为空，操作取消。[/red]")
                sys.exit(1)
        except KeyboardInterrupt: # 用户按 Ctrl+C 取消 InquirerPy 提示
            rich_print("\n[yellow]⚠️ 操作已取消。[/yellow]")
            sys.exit(0) # 用户取消是正常退出，返回码0
        except Exception as e: # 捕获 inquirer 执行过程中的其他异常
             rich_print(f"[red]❌ Token 输入过程中发生错误:[/red] [yellow]{e}[/yellow]")
             sys.exit(1)

        config_data = {"token": token}
        try:
            # 确保配置文件的目录存在
            config_dir = os.path.dirname(CONFIG_FILE_PATH)
            os.makedirs(config_dir or '.', exist_ok=True) # . 表示当前目录，如果路径是文件名
            # 使用绝对路径写入配置文件
            with open(CONFIG_FILE_PATH, "w") as f:
                yaml.dump(config_data, f, default_flow_style=False) # 使用 default_flow_style=False 使得 YAML 更易读
            rich_print(f"[green]✅ 新配置文件写入成功:[/green] [cyan]{CONFIG_FILE_PATH}[/cyan]")
        except Exception as e:
            rich_print(f"[red]❌ 配置文件写入失败:[/red] [yellow]{e}[/yellow]")
            sys.exit(1)
        return token
    except Exception as e: # 捕获 init_config 中未被特定处理的异常
        rich_print(f"[red]❌ 初始化配置时发生未知错误:[/red] [yellow]{e}[/yellow]")
        sys.exit(1)


# get_config 改为同步函数，使用 httpx.Client
def get_config(token: str, node: str) -> Optional[str]:
    """同步获取指定节点的配置。"""
    url = f"{TUNNEL_CONFIG_URL}?token={token}&node={node}"
    rich_print(f"[yellow]正在获取节点 '{node}' 的配置...[/yellow]")
    try:
        # 使用同步 httpx.Client
        with httpx.Client() as client:
            response = client.get(url, timeout=10.0) # 添加超时
            response.raise_for_status() # 检查 HTTP 状态码 (2xx)

            data = response.json() # 直接调用 json()
            config_data = data.get("data") # 获取data字段

            # 检查 data 部分是否是字符串且非空
            if not isinstance(config_data, str) or not config_data:
                # 即使状态码是200，API返回的数据也可能无效或格式错误
                # 尝试从响应中获取可能的错误信息或状态
                api_state = data.get("state", "unknown")
                api_msg = data.get("msg", "未获取到有效的配置数据")
                # 优先使用 API 返回的 msg，如果 state 不是 success
                if api_state != "success":
                    raise APIError(f"API 返回错误 ({api_state}): {api_msg}")
                else:
                    # state 是 success 但 data 无效，可能是 API Bug 或 Unexpected
                    raise APIError(f"API 返回数据无效或格式错误 (state: {api_state}, msg: {api_msg})")

            rich_print(f"[green]✅ 成功获取节点 '{node}' 配置。[/green]")
            return config_data
    except httpx.HTTPStatusError as e:
        rich_print(f"[red]❌ HTTP 错误获取配置 ({e.response.status_code}):[/red] [yellow]{e}[/yellow]")
        if e.response.status_code in (401, 403): # 401 Unauthorized, 403 Forbidden
             rich_print("[yellow]请检查你的 Token 是否有效或已过期。[/yellow]")
        elif e.response.status_code == 404:
             rich_print(f"[yellow]节点 '{node}' 可能不存在或已下线。[/yellow]")
        else:
             rich_print(f"[yellow]API 返回了非成功的状态码: {e.response.status_code}[/yellow]")
    except httpx.RequestError as e:
        rich_print(f"[red]❌ 网络请求失败获取配置:[/red] [yellow]{e}[/yellow]")
        rich_print("[yellow]请检查网络连接或 API 地址是否正确。[/yellow]")
    except APIError as e:
        rich_print(f"[red]❌ API 错误获取配置:[/red] [yellow]{e}[/yellow]")
    except Exception as e:
        rich_print(f"[red]❌ 未知错误获取配置:[/red] [yellow]{e}[/yellow]")
    return None

# get_node_list 改为同步函数，使用 httpx.Client
def get_node_list(token: str) -> List[str]: # 使用 List[str] 更精确
    """同步获取节点列表。"""
    url = f"{TUNNEL_URL}?token={token}"
    rich_print("[yellow]正在获取节点列表...[/yellow]")
    try:
        # 使用同步 httpx.Client
        with httpx.Client() as client:
            response = client.get(url, timeout=10.0) # 添加超时
            response.raise_for_status() # 检查 HTTP 状态码 (2xx)

            data = response.json() # 直接调用 json()

            # 检查 API 返回的 state 是否为 success
            if data.get("state") != "success":
                # 如果API返回了错误信息，使用它；否则使用通用错误信息
                raise APIError(data.get("msg", "Token 错误或 API 调用失败"))

            nodes_data: Any = data.get("data") # 使用 Any 标记初始类型可能不确定

            # 检查 data 部分是否是列表且非空
            if not isinstance(nodes_data, list) or not nodes_data:
                 # 尝试从响应中获取可能的错误信息或状态
                api_state = data.get("state", "unknown")
                api_msg = data.get("msg", "API 返回数据格式错误或列表为空")
                # 如果 state 是 success 但 data 是空的或格式不对
                if data.get("state") == "success":
                    rich_print("[yellow]⚠️ API 返回的节点列表为空或格式异常。[/yellow]")
                    return [] # 如果 state 成功但列表为空，返回空列表而不是抛异常
                else:
                    # state 不成功且 data 有问题
                     raise APIError(f"API 返回错误 ({api_state}): {api_msg}")

            # 过滤出包含 'node' 键的字典，并提取 node 值
            nodes = [node["node"] for node in nodes_data if isinstance(node, dict) and "node" in node and isinstance(node["node"], str)] # 确保 node 是字符串

            if not nodes:
                rich_print("[yellow]⚠️ 过滤后节点列表为空。[/yellow]")
            else:
                 rich_print(f"[green]✅ 成功获取 {len(nodes)} 个节点。[/green]")

            return nodes
    except httpx.HTTPStatusError as e:
        rich_print(f"[red]❌ HTTP 错误获取节点列表 ({e.response.status_code}):[/red] [yellow]{e}[/yellow]")
        if e.response.status_code in (401, 403):
             rich_print("[yellow]请检查你的 Token 是否有效或已过期。[/yellow]")
        else:
             rich_print(f"[yellow]API 返回了非成功的状态码: {e.response.status_code}[/yellow]")
    except httpx.RequestError as e:
        rich_print(f"[red]❌ 网络请求失败获取节点列表:[/red] [yellow]{e}[/yellow]")
        rich_print("[yellow]请检查网络连接或 API 地址是否正确。[/yellow]")
    except APIError as e:
        rich_print(f"[red]❌ API 错误获取节点列表:[/red] [yellow]{e}[/yellow]")
    except Exception as e:
        rich_print(f"[red]❌ 未知错误获取节点列表:[/red] [yellow]{e}[/yellow]")
    return []


# --- Typer 应用实例 ---
app = typer.Typer(help="Frp 客户端配置和运行工具.") # 添加整体帮助信息

# --- Typer 命令 ---

@app.command(help="运行 frpc 可执行文件.") # 添加命令帮助信息
def run(): # <<< run 命令保持同步 def
    """
    运行 frpc 可执行文件.

    frpc 可执行文件需要放在与脚本同目录下的 frp/ 子目录中。
    程序会尝试在 frp 目录下启动它，frpc.ini 文件也应位于该目录。
    """
    rich_print(f"[yellow]尝试在目录 [cyan]{FRP_DIR_PATH}[/cyan] 中启动可执行文件 [cyan]{FRPC_EXE_PATH}[/cyan] ...[/yellow]")
    rich_print("[yellow]提示：按 Ctrl+C 终止 frpc 进程。[/yellow]") # frpc 是长时间运行的进程

    # 检查 frpc.ini 文件是否存在
    if not os.path.exists(FRPC_INI_PATH):
        rich_print(f"[red]❌ 错误: 找不到配置文件 [cyan]{FRPC_INI_PATH}[/cyan]。[/red]")
        rich_print("[yellow]请先运行 'config' 命令生成配置文件。[/yellow]")
        sys.exit(1)

    # 检查 frpc 可执行文件是否存在
    if not os.path.exists(FRPC_EXE_PATH):
         rich_print(f"[red]❌ 错误: 找不到可执行文件 [cyan]{FRPC_EXE_PATH}[/cyan]。[/red]")
         rich_print(f"[yellow]请确保文件存在且放在正确位置 ({FRP_DIR_NAME})。[/yellow]")
         sys.exit(1)

    try:
        # 使用 subprocess.run 启动 frpc，cwd 设置为 frp 目录
        process = subprocess.run(
            [FRPC_EXE_PATH, "-c", FRPC_INI_PATH], # 将 frpc.ini 作为参数传递，更明确
            cwd=os.path.dirname(FRPC_EXE_PATH),  # 在 frpc.exe 所在目录运行
        )

        # 如果 subprocess.run 结束 (通常因为用户终止或进程崩溃)
        rich_print(f"[green]🚀 frpc 进程已停止。[/green] 返回码: {process.returncode}")

    except FileNotFoundError:
         rich_print(f"[red]❌ 错误: 找不到可执行文件 [cyan]{FRPC_EXE_PATH}[/cyan]。[/red]")
         rich_print(f"[yellow]请确保文件存在且有执行权限，并且放在正确位置 ({FRP_DIR_NAME})。[/yellow]")
         sys.exit(1)
    except PermissionError:
         rich_print(f"[red]❌ 错误: 没有执行文件 [cyan]{FRPC_EXE_PATH}[/cyan] 的权限。[/red]")
         rich_print("[yellow]请检查文件权限。[/yellow]")
         sys.exit(1)
    except KeyboardInterrupt:
        # 用户在运行frpc过程中按下Ctrl+C
        rich_print("\n[yellow]⚠️ frpc 进程已收到终止信号。[/yellow]")
        sys.exit(0) # 认为用户终止是正常退出
    except Exception as e:
        rich_print(f"[red]❌ 启动 frpc 失败:[/red] [yellow]{e}[/yellow]")
        sys.exit(1)


@app.command(help="配置 frpc.ini 文件.") # 添加命令帮助信息
# 将 config 命令标记为 def，确保它是同步的
def config(): # <<< config 命令改为同步 def
    """
    配置 frpc.ini 文件.

    引导用户选择节点并获取对应的 frpc.ini 配置。
    """
    try:
        # 1. 初始化配置并获取 token (调用同步函数)
        token = init_config()
        # init_config 内部已处理 token 缺失或错误并退出，此处无需额外检查 token 是否为 None

        # 2. 获取节点列表 (调用同步函数)
        nodes = get_node_list(token)

        if not nodes:
            rich_print("[red]❌ 未获取到可用的节点列表。[/red]")
            rich_print("[yellow]请检查你的 token 是否有效，或 API 服务是否可用。[/yellow]")
            sys.exit(1) # 如果是强制需要节点，则退出

        # 3. 使用 InquirerPy 提示用户选择节点 (同步操作，直接调用)
        rich_print("\n[green]请选择一个节点:[/green]")
        chosen_node = None
        try:
            # 直接调用 execute，因为整个函数是同步的
            chosen_node = inquirer.select(
                message="选择节点:",
                choices=nodes,
                qmark="❓", # 可以自定义问题标记
                long_instruction="使用方向键选择节点，回车确认。" # 长指令提示
            ).execute()

        except KeyboardInterrupt: # 用户按 Ctrl+C 取消 InquirerPy 提示
             rich_print("\n[yellow]⚠️ 操作已取消。[/yellow]")
             sys.exit(0) # 用户取消，正常退出
        except Exception as e: # 捕获 inquirer 执行过程中的其他异常
             rich_print(f"[red]❌ 节点选择过程中发生错误:[/red] [yellow]{e}[/yellow]")
             sys.exit(1)

        if not chosen_node: # 如果用户没有选择任何项（例如，列表为空或取消），尽管 InquirerPy 通常会抛异常而不是返回 None
             rich_print("[yellow]⚠️ 没有选择节点，操作取消。[/yellow]")
             sys.exit(0) # 用户没有选择，正常退出

        rich_print(f"[green]✅ 已选择节点:[/green] [cyan]{chosen_node}[/cyan]")

        # 4. 获取选定节点的配置 (调用同步函数)
        config_data = get_config(token=token, node=chosen_node)

        if not config_data:
            # get_config 内部已打印错误并返回 None，此处直接退出
            sys.exit(1)

        # 5. 写入配置文件 (同步操作)
        try:
            # 确保 frp 目录存在，使用绝对路径
            os.makedirs(os.path.dirname(FRPC_INI_PATH), exist_ok=True)  # 确保目录存在
            # 使用 frpc.ini 文件的绝对路径写入
            with open(FRPC_INI_PATH, "w") as f:
                f.write(config_data)
            rich_print(f"[green]✅ 成功生成 frpc.ini 配置文件:[/green] [cyan]{FRPC_INI_PATH}[/cyan]")
        except Exception as e:
            rich_print(f"[red]❌ 写入 [cyan]{FRPC_INI_PATH}[/cyan] 失败:[/red] [yellow]{e}[/yellow]")
            sys.exit(1)

    except Exception as e:
        # 捕获 config() 中未被特定try/except处理的任何其他异常
        rich_print(f"[red]❌ 配置过程中发生未知错误:[/red] [yellow]{e}[/yellow]")
        sys.exit(1)


# --- 主入口点 ---
# Typer 应用的入口点
if __name__ == "__main__":
    # Typer 会检测命令是否为 async def。如果所有命令都是 def，则不会运行事件循环。
    app()