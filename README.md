# chmlfrp-cli

一个用来快速配置和运行 frpc 的命令行工具。

## 简介

`chmlfrp` 是一个基于 Python 的 CLI 工具，旨在简化 frpc (frp 客户端) 的配置和启动过程。 它通过交互式界面引导用户选择节点，从 API 获取配置，并生成 `frpc.ini` 文件，最后运行 `frpc` 可执行文件。

## 功能特性

*   **交互式配置：** 通过友好的命令行界面，引导用户输入 Token 并选择 frp 节点。
*   **自动获取配置：**  从 API 自动获取选定节点的 `frpc.ini` 配置。
*   **快速启动：**  一键运行 `frpc`，简化手动配置和启动的繁琐步骤。

## 使用方法

'''

### 1. 安装
```bash
git clone https://github.com/drizzlexlh/chmlfrp-cli.git
cd chmlfrp-cli
pip install .
```
### 2.启动
```bash
chml
```
#### 命令:
```bash
chml config   #配置隧道
```
```bash
chml run   #启动！
```
```bash
chml download   #下载chmlfrp！
```
需要在chmlfrp官网注册或登录账号后获取token  
#### chmlfrp官网地址:
```bash
https://chmlfrp.cn/
```
