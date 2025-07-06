use reqwest;
use tokio;
use std::{fs, io::Write, path::{Path, PathBuf}};
use lazy_static::lazy_static;
use std::collections::{HashMap};
use serde::{Serialize, Deserialize};
use inquire::{self, Select, MultiSelect};
use colored::*;
use indicatif::{ProgressBar, ProgressStyle};
use futures_util;
use zip;
use flate2::read::GzDecoder; // 引入 GzDecoder，用于解压 gzip
use tar::Archive;

//----------global value
lazy_static! {
    static ref CHML_GET_INFO_URL:String = "https://cf-v2.uapis.cn/tunnel".to_string();
    static ref CHML_GET_CONFIGFILE_URL:String = "https://cf-v2.uapis.cn/tunnel_config".to_string();
    static ref CHML_GET_ALLNODE_URL: String = "https://cf-v2.uapis.cn/node".to_string(); 
    static ref CHML_CREATE_NODE_URL: String = "https://cf-v2.uapis.cn/create_tunnel".to_string();
    static ref PROJECT_ROOT_DIR: PathBuf = {
        let dir = std::env::current_dir().expect("无法获取当前工作目录，程序无法启动！");
        dir
    };
    static ref TOKEN_JSON_FILE:PathBuf = {
        let dir = PROJECT_ROOT_DIR.join("token.js");
        dir
    };
    static ref CHML_APP_INSTALL_URL: HashMap<String, HashMap<String, String>> = {
        let mut data = HashMap::new();

        // Windows
        let mut windows_data = HashMap::new();
        windows_data.insert(String::from("x86_64"), String::from("https://www.chmlfrp.cn/dw/ChmlFrp-0.51.2_240715_windows_amd64.zip"));
        windows_data.insert(String::from("aarch64"), String::from("https://www.chmlfrp.cn/dw/ChmlFrp-0.51.2_240715_windows_arm64.zip"));
        data.insert(String::from("windows"), windows_data);

        // Linux
        let mut linux_data = HashMap::new();
        linux_data.insert(String::from("x86_64"), String::from("https://www.chmlfrp.cn/dw/ChmlFrp-0.51.2_240715_linux_amd64.tar.gz"));
        linux_data.insert(String::from("aarch64"), String::from("https://www.chmlfrp.cn/dw/ChmlFrp-0.51.2_240715_linux_arm64.tar.gz"));
        data.insert(String::from("linux"), linux_data);

        // FreeBSD
        let mut freebsd_data = HashMap::new();
        freebsd_data.insert(String::from("x86_64"), String::from("https://www.chmlfrp.cn/dw/ChmlFrp-0.51.2_240715_freebsd_amd64.tar.gz"));
        data.insert(String::from("freedbs"), freebsd_data);

        //macOS
        let mut darwin_data = HashMap::new();
        darwin_data.insert(String::from("x86_64"), String::from("https://www.chmlfrp.cn/dw/ChmlFrp-0.51.2_240715_darwin_amd64.tar.gz"));
        darwin_data.insert(String::from("aarch64"), String::from("https://www.chmlfrp.cn/dw/ChmlFrp-0.51.2_240715_darwin_arm64.tar.gz"));
        data.insert(String::from("macos"), darwin_data);

        data // 返回构建好的 HashMap
    };
}

//main
#[tokio::main]
async fn main(){
    let args: Vec<String> = std::env::args().collect();
    let token:String = get_token(false).await;

    if args.len() > 1{
        let val = args.get(1).expect("index error");
        if val == "cfg"{
            set_chmlfrp_config(token.as_str()).await.expect("配置隧道错误");
        }else if val == "run" {
            run_chml().await.expect("chmlfrp启动失败");
        }else if val == "clear" {
            clear_cache();
        }
    }
    else {
        init_chml().await.expect("初始化错误");
    }
}

//----------my_struct

//隧道信息的response
#[derive(Debug, Deserialize, Clone)]
pub struct TunnelData {
    pub id: u32,
    pub name: String,
    pub localip: String,
    #[serde(rename = "type")] // 注意: Rust 关键字 "type" 需要特殊处理
    pub tunnel_type: String, // 命名为 tunnel_type 避免与 Rust 关键字冲突
    pub nport: u16,
    pub dorp: String, // 看起来像字符串，尽管是数字
    pub node: String,
    pub state: String, // 尽管是 "true"/"false"，但在 JSON 中是字符串，所以用 String
    pub userid: u32,
    pub encryption: String,
    pub compression: String,
    pub ap: String,
    pub uptime: Option<String>, // 注意: null 值对应 Option<T>
    pub client_version: Option<String>, // 注意: "null" 字符串和 null 值
    pub today_traffic_in: u64,
    pub today_traffic_out: u64,
    pub cur_conns: u32,
    pub nodestate: String,
    pub ip: String,
}

//chml全部节点信息的response
#[derive(Debug, Deserialize, Clone)]
pub struct ChmlFrpNodeInfo {
    pub msg: String,
    pub code: u16, // 状态码通常是数字
    pub data: Vec<TunnelData>, // 关键：'data' 字段是一个包含多个 TunnelData 结构体的向量
    pub state: String, // "success" 是字符串
}

//chml配置文件的response
#[derive(Debug, Serialize, Deserialize)]
pub struct ChmlFrpConfigData {
    pub msg: String,
    pub code: u16,
    pub data: String, // 注意：这里是原始的INI字符串，稍后需要手动解析
    pub state: String,
}

//----------my_func

//初始化配置
async fn init_chml() -> Result<(), Box<dyn std::error::Error>>{
    get_token(true).await;

    let system_type: &str = std::env::consts::OS;
    let arch_type: &str = std::env::consts::ARCH;

    //在获取系统对应版本的chmlfrp软件
    let chml_download_url:String = CHML_APP_INSTALL_URL.get(system_type) 
        .and_then(|inner_map| inner_map.get(arch_type)).expect("获取url错误").clone();
    let zipfile_path: Vec<&str> = chml_download_url.split('/').collect();
    let zipfile_path: &str = *zipfile_path.last().expect("文件获取错误");

    //解析获取download路径
    let root_path = PROJECT_ROOT_DIR.to_str().expect("路径解析字符串错误");
    let download_path = PROJECT_ROOT_DIR.clone().join("download");
    if !download_path.exists(){
        std::fs::create_dir_all(download_path.clone()).expect("download目录创建失败");
    }
    let download_file_path = download_path.join(zipfile_path);
    let download_file_path_str = download_file_path.to_str().expect("路径解析字符串错误");

    //下载chmlfrp
    if !std::path::PathBuf::from(download_file_path_str).exists() {
        println!("{}", "正在下载chmlfrp..".green());
        download_file(chml_download_url.to_string(), download_file_path_str.to_string()).await?;
    }
    else {
        println!("{}", "检测到chmlfrp已经存在".green());
    }

    //解压chmlfrp
    if download_file_path_str.ends_with("zip"){
        println!("{}", "解压zip文件中...".yellow());
        unzip_file(download_file_path_str, root_path)?;
        println!("{}", "解压zip完成...".green());
    }else {
        println!("{}", "解压tar.gz文件中...".yellow());
        unpack_tar_gz(download_file_path_str, root_path)?;
        println!("{}", "解压tar.gz完成...".green());
    }

    //重命名软件的路径
    for entry_result in std::fs::read_dir(root_path)?{
        let entry = entry_result?;
        let path = entry.path();
        let new_path = PathBuf::from(root_path).join("chmlfrp");

        if path.is_dir(){
            if path.file_name().expect("路径转化错误").to_str().expect("路径转化错误").to_string().starts_with("ChmlFrp-"){
                if new_path.clone().exists(){
                    println!("{}", "正在移除多余文件夹");
                    fs::remove_dir_all(new_path.clone()).expect("移除多余文件错误");
                }
                println!("{}", "正在重命名chmlfrp文件夹");
                fs::rename(path, new_path).expect("重命名路径错误");
            }
        }
    }
    println!("{}", "搞定！".green());
    Ok(())
}

//获取token
async fn get_token(need_get_token: bool) ->String{
    let token = if TOKEN_JSON_FILE.exists(){
        let token:String = std::fs::read_to_string(TOKEN_JSON_FILE.to_str().expect("文件路径转化字符串错误")).expect("读取文件错误");

        let is_reget: bool = if need_get_token{
            inquire::Confirm::new("token配置已经存在 需要重新获取?").with_default(false).prompt().unwrap_or(false)
        }else {
            false
        };
        if is_reget{
            let token:String = inquire::Text::new("请输入你的token:").prompt().expect("输入为空...");
            std::fs::write(TOKEN_JSON_FILE.to_str().expect("文件路径转字符串失败"), token.clone()).expect("写入token失败");
            return token;
        }
        token
    } else {
        let token:String = inquire::Text::new("请输入你的token:").prompt().expect("输入为空...");
        std::fs::write(TOKEN_JSON_FILE.to_str().expect("文件路径转字符串失败"), token.clone()).expect("写入token失败");
        token
    };
    token
}

//下载文件
async fn download_file(url:String, file_path:String) -> Result<(), Box<dyn std::error::Error>>{
    let client = reqwest::Client::new();
    let response = client.get(url).send().await?;
    let total_size = response.content_length().unwrap_or(0);
    let pb = ProgressBar::new(total_size);
    pb.set_style(ProgressStyle::default_bar()
       .template("{spinner:.green} [{elapsed_precise}] [{wide_bar:.cyan/blue}] {bytes}/{total_bytes} ({eta})")
       .unwrap()
       .progress_chars("#>-"));

    let mut file = std::fs::File::create(file_path)?;
    let mut downloaded = 0;
    let mut stream = response.bytes_stream();

    while let Some(chunk_result) = futures_util::StreamExt::next(&mut stream).await {
        let chunk = chunk_result?;
        file.write_all(&chunk)?;
        let new = std::cmp::min(downloaded + (chunk.len() as u64), total_size);
        downloaded = new;
        pb.set_position(new);
    }
    Ok(())
}

//解压zip
fn unzip_file(zip_file_path: &str, destination_dir: &str) -> Result<(), Box<dyn std::error::Error>>{
    let zip_file = std::fs::File::open(zip_file_path)?;
    let mut archive = zip::ZipArchive::new(zip_file)?;
    
    for i in 0..archive.len(){
        let mut file = archive.by_index(i)?;

        let outpath = match file.enclosed_name() {
            Some(path) => path.to_owned(),
            None => continue,
        };

        let outpath = Path::new(destination_dir).join(outpath);
        if file.name().ends_with("/"){
            fs::create_dir_all(outpath)?;
        }else{
            if let Some(p) = outpath.parent(){
                if !p.exists(){
                    fs::create_dir_all(p)?;
                }
            }
            let mut outfile = fs::File::create(&outpath)?;
            std::io::copy(&mut file, &mut outfile)?;
        }
    }
    Ok(())
}

//解压tar.gz
fn unpack_tar_gz(tar_gz_file_path: &str, destination_dir: &str) -> Result<(), Box<dyn std::error::Error>> {
    fs::create_dir_all(destination_dir)?;
    let tar_gz = fs::File::open(tar_gz_file_path)?;

    let tar = GzDecoder::new(tar_gz);

    let mut archive = Archive::new(tar);

    archive.unpack(destination_dir)?;

    Ok(())
}

//获取node信息
async fn get_chmlfrp_node_info(token: &str) ->Result<ChmlFrpNodeInfo, Box<dyn std::error::Error>>{
    let chmlfrp_node_info_url = format!("{}?token={}", CHML_GET_INFO_URL.to_string(), token);
    let response = reqwest::get(chmlfrp_node_info_url).await?;
    let data: ChmlFrpNodeInfo = response.json().await?;
    Ok(data)
}

//获取配置文件
async fn set_chmlfrp_config(token: &str) ->Result<(), Box<dyn std::error::Error>>{

    //获取全部node信息 并且按照nodename归类
    let nodes: Vec<TunnelData> = get_chmlfrp_node_info(token).await?.data;
    let mut data: HashMap<String, Vec<TunnelData>> = HashMap::new();
    for node in nodes{
        if !data.contains_key(&node.node.clone()){
            data.insert(node.node.clone(), Vec::new());
        }
        data.get_mut(&node.node.clone()).expect("获取配置失败").push(node.clone());
    }

    //选择节点
    let selected_node_name = Select::new("选择一个节点:", data.keys().cloned().collect()).prompt().expect("选择错误哦");
    let selected_nodes = data.get(&selected_node_name).expect("获取节点错误");
    
    //获取已选节点的全部隧道信息
    let mut tunnel_map = HashMap::new();
    for temp_node in selected_nodes{
        let tunnel_str = format!("name: {:<w_n$}  local_port: {:<w_p$}  addr: {}:{:<w_nip$}  state: {:<w_s$}", temp_node.name.yellow(), temp_node.nport.to_string().yellow(), temp_node.ip.yellow(), temp_node.dorp.yellow(), temp_node.state.yellow(), w_n=16, w_p=6, w_nip=6, w_s=7);

        tunnel_map.insert(tunnel_str, temp_node.name.clone());
    }

    //选择隧道
    let selected_tunnel_info = MultiSelect::new("选择一个隧道吧:", tunnel_map.keys().collect()).prompt().expect("隧道选择错误");
    let mut selected_tunnel_names: Vec<String> = Vec::new();

    //获取选择的隧道
    for tunnel_info in selected_tunnel_info{
        let tunnel_name = tunnel_map.get(tunnel_info).expect("获取隧道错误").clone();
        selected_tunnel_names.push(tunnel_name);
    }
    
    //获取隧道的配置文件
    let get_config_url = format!("{}?token={}&node={}&tunnel_names={}", CHML_GET_CONFIGFILE_URL.to_string(), token, selected_node_name, selected_tunnel_names.join(","));
    let response = reqwest::get(get_config_url).await?;

    //写入配置
    if response.status().is_success(){
        let config_data: ChmlFrpConfigData = response.json().await?;
        let config_data = config_data.data;
        
        let frpc_ini_path = PROJECT_ROOT_DIR.clone().join("chmlfrp").join("frpc.ini");
        fs::write(frpc_ini_path, config_data).expect("写入配置文件失败");
        println!("{}", "配置文件写入成功".green());
    }else {
        println!("{}", "获取配置文件失败".red());
    }
    Ok(())
}

//清除缓存
fn clear_cache(){
    let download_path = PROJECT_ROOT_DIR.clone().join("download");
    if download_path.exists(){
        fs::remove_dir_all(download_path).expect("清除不了");
    }
    else {
        println!("{}", "缓存已经空了哦".yellow());
    }
}

//启动chmlfrp
async fn run_chml() ->Result<(), Box<dyn std::error::Error>>{
    let frpc_path = PROJECT_ROOT_DIR.clone().join("chmlfrp").join("frpc");
    let frpc_ini_path = PROJECT_ROOT_DIR.clone().join("chmlfrp").join("frpc.ini");
    let mut command = std::process::Command::new(frpc_path);
    println!("{}", "正在运行chmlfrp".yellow());
    command.arg("-c").arg(frpc_ini_path); 
    command.spawn()?.wait()?;
    Ok(())
}

//获取已配置信息
//不想写了

//