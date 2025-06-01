from typer import Typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress
from InquirerPy import inquirer
import json
import httpx
import pathlib
import tarfile, zipfile
import shutil
import subprocess
import os, sys
console = Console(color_system="256")
app = Typer()


#global
PROJECT_DIR=pathlib.Path(os.path.dirname(sys.argv[0]))
APP_PATH = pathlib.Path(PROJECT_DIR / "chmlapp/")
CHML_PATH = pathlib.Path(APP_PATH / "chmlfrp/")
CHML_INI_FILE = CHML_PATH / "frpc.ini"
CHML_FRP_FILE = CHML_PATH / "frpc"
CONFIG_FILE = pathlib.Path(PROJECT_DIR / "config.json")
g_token = ""
TUNNEL_INFO_URL = "https://cf-v2.uapis.cn/tunnel" #get请求 form参数 token
TUNNEL_GETCONFIG_URL = "https://cf-v2.uapis.cn/tunnel_config" #form参数 token, node, [可选]tunnel_names
TUNNEL_CREATE_URL = "https://cf-v2.uapis.cn/create_tunnel"
TUNNEL_GETNODE_URL = "https://cf-v2.uapis.cn/node"

chmlfrp_app_download_data = {
    "windows": {
        "amd64": "https://www.chmlfrp.cn/dw/ChmlFrp-0.51.2_240715_windows_amd64.zip",
        "386": "https://www.chmlfrp.cn/dw/ChmlFrp-0.51.2_240715_windows_386.zip",
        "arm64": "https://www.chmlfrp.cn/dw/ChmlFrp-0.51.2_240715_windows_arm64.zip"
        },
    "linux": {
        "amd64": "https://www.chmlfrp.cn/dw/ChmlFrp-0.51.2_240715_linux_amd64.tar.gz",
        "386": "https://www.chmlfrp.cn/dw/ChmlFrp-0.51.2_240715_linux_386.tar.gz",
        "arm": "https://www.chmlfrp.cn/dw/ChmlFrp-0.51.2_240715_linux_arm.tar.gz",
        "arm64": "https://www.chmlfrp.cn/dw/ChmlFrp-0.51.2_240715_linux_arm64.tar.gz"
        },
    "freedbs": {
        "amd64": "https://www.chmlfrp.cn/dw/ChmlFrp-0.51.2_240715_freebsd_amd64.tar.gz",
        "386": "https://www.chmlfrp.cn/dw/ChmlFrp-0.51.2_240715_freebsd_386.tar.gz"
        },
    "darwin": {
        "amd64": "https://www.chmlfrp.cn/dw/ChmlFrp-0.51.2_240715_darwin_amd64.tar.gz",
        "arm64": "https://www.chmlfrp.cn/dw/ChmlFrp-0.51.2_240715_darwin_arm64.tar.gz"
    }
}


def download_chml():
    my_system = inquirer.select(message="请选择你的系统:", choices=[sys_name for sys_name in chmlfrp_app_download_data]).execute()
    my_architecture = inquirer.select(message="请选择你的系统:", choices=[sys_architecture for sys_architecture in chmlfrp_app_download_data[my_system]]).execute()
    download_url = chmlfrp_app_download_data[my_system][my_architecture]
    
    chml_zip_filename = f".{download_url[download_url.rfind('/'):]}"
    
    if APP_PATH.exists():  #清空一次文件夹
        shutil.rmtree(APP_PATH)
        
    APP_PATH.mkdir()
    
    console.print("[yellow]下载chmlfrp中...")

    try:
        file_size = int(httpx.head(download_url).headers.get("Content-Length", 0))
        with Progress() as progress:
            task = progress.add_task("downloading...", total=file_size)
            with httpx.stream("get", download_url) as response, open(chml_zip_filename, 'bw') as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)
                    progress.update(task, advance=len(chunk))
    except Exception as e:
        console.print("[red]下载失败...")
        console.print(e)
        exit(1)
    console.print("[green]下载完成！")
    
    
    console.print("[yellow]解压中...")
    unpackage_file = None
    if chml_zip_filename.endswith("zip"):
        unpackage_file = zipfile.ZipFile(chml_zip_filename)
    elif chml_zip_filename.endswith("tar.gz"):
        unpackage_file = tarfile.open(chml_zip_filename)
    
    unpackage_file.extractall(APP_PATH)
    
    next(APP_PATH.iterdir(), None).rename(APP_PATH / "chmlfrp")
    
    unpackage_file.close()
    console.print("[green]解压完成！")
    os.remove(chml_zip_filename)
    

def set_token():
    g_token = console.input("[green]请输入你的[red]token[white]:")
    data = {"token": g_token}
    with open(CONFIG_FILE, 'w') as f:
        json.dump(data, f, indent=True)
    


#初始化------------------------------
def init_config():
    #检查文件
    if not CHML_INI_FILE.exists():
        console.print("[yellow]未检测到chmlfrp 准备下载...")
        download_chml()
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            global g_token
            data = json.load(f)
            g_token = data["token"]
    except:
        console.print("[red i]加载token失败...")
        set_token()
        
    
init_config()
    


@app.command(name="download", help="下载chmlfrp")
def download():
    download_chml()

@app.command()
def token():
    set_token()

@app.command("config", help="获取隧道配置文件")
def config():
    nodes = {}
    try:
        console.print("[yellow]正在获取节点信息...")
        nodes_data = httpx.get(f"{TUNNEL_INFO_URL}?token={g_token}").raise_for_status().json()["data"]
        #判断隧道节点 并作为key, 值为隧道全部信息
        for node in nodes_data:
            if node["node"] not in nodes:
                nodes[node["node"]] = [node]
            else:
                nodes[node["node"]].append(node)
            
    except:
        console.print("[red]节点获取失败... [green]请检查网络状态或者[yellow]token[green]是否填写正确。")
        exit(1)
    
    console.print("[green]节点获取成功 喵~")
    
    
    #检查节点列表是否为空
    if not nodes:
        console.print("[red]你没有创建任何节点 喵... 快去创建吧")
        exit(0)
        
    #选择节点
    selected_node_name = inquirer.select(message="请选择一个节点:", choices=[node_name for node_name in nodes]).execute()
    
    
    
    #选择节点
    
    selected_tunnel_names = [] #存储选择的节点名字
    if inquirer.confirm(message="详细选择隧道? (默认为全选)", default=False).execute():
        try:
            selected_tunnel_names = inquirer.checkbox(
                message="请选择节点:", 
                choices=[node["name"] for node in nodes[selected_node_name] if node["name"] not in selected_tunnel_names]
                ).execute()
        except:
            console.print("[green]节点选完了喵... 下一步吧！")
            
    #获取配置文件
    
    console.print("[yellow]正在获取配置文件...")
    
    
    config_content = "" #配置文件内容
    try:
        if selected_tunnel_names: #判断有没有选择隧道 没选择则全选
            selected_tunnel_names_str = "" #用来填到get请求的tunnel_names参数
            for name in selected_tunnel_names:
                selected_tunnel_names_str += f"{name},"
        
            config_content = httpx.get(f"{TUNNEL_GETCONFIG_URL}?token={g_token}&node={selected_node_name}&tunnel_names={selected_tunnel_names_str}").raise_for_status().json()["data"] #只获取选择的隧道
        else:
            config_content = httpx.get(f"{TUNNEL_GETCONFIG_URL}?token={g_token}&node={selected_node_name}").raise_for_status().json()["data"]  #获取全部隧道
    except Exception as e:
        console.print("[red]获取配置文件失败 请重试...")
        console.print(e)
        exit(1)
            
    console.print("[green]获取配置文件成功 喵~")
        
        
    console.print("[yellow]写入配置文件...")
    try:
        with open(CHML_INI_FILE, 'w') as f:
            f.write(config_content)
    except Exception as e:
        console.print("[red]配置文件写入失败...")
        console.print(e)
        exit(0)
    console.print("[green]配置文件写入成功 喵~")
    
    result_config_info_table = Table(show_header=True, title="当前配置的隧道", header_style="bold white") #完成配置的节点信息
    result_config_info_table.add_column("隧道名称", style="magenta")
    result_config_info_table.add_column("隧道类型", style="blue")
    result_config_info_table.add_column("内网端口", style="blue")
    result_config_info_table.add_column("url", style="blue")
    for node in nodes[selected_node_name]:
        if not selected_tunnel_names:
            result_config_info_table.add_row(node["name"], node["type"], str(node["nport"]), f"{node['ip']}:{node['dorp']}")
        elif node["name"] in selected_tunnel_names:
            result_config_info_table.add_row(node["name"], node["type"], str(node["nport"]), f"{node['ip']}:{node['dorp']}")
            
    console.print(result_config_info_table)
    
    
@app.command(name="run", help="启动！")
def run():
    subprocess.run([CHML_FRP_FILE], cwd=CHML_PATH)
    os.system()
    
    
    
if __name__ == "__main__":
    app()