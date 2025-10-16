# 使用 Daytona 沙箱的智能体（Agent）

## 前置条件

* 激活你的 Python 环境

  ```bash
  conda activate 'Your OpenManus python env'
  ```
* 安装依赖

  ```bash
  pip install daytona==0.21.8 structlog==25.4.0
  ```

---

## 设置与运行步骤

### 1️⃣ 配置 Daytona

```bash
cd OpenManus
cp config/config.example-daytona.toml config/config.toml
```

### 2️⃣ 获取 Daytona API Key

前往 [https://app.daytona.io/dashboard/keys](https://app.daytona.io/dashboard/keys)，创建你的 API Key。

### 3️⃣ 在配置文件中设置 API Key

打开 `config.toml`，在其中填写你的 key：

```toml
# Daytona 配置
[daytona]
daytona_api_key = ""                         # 在此填写你的 API Key
#daytona_server_url = "https://app.daytona.io/api"
#daytona_target = "us"                        # Daytona 目前支持的区域：美国 (us)、欧洲 (eu)
#sandbox_image_name = "whitezxj/sandbox:0.1.0"  # 若不使用此默认镜像，沙箱工具可能无法正常工作
#sandbox_entrypoint = "/usr/bin/supervisord -n -c /etc/supervisor/conf.d/supervisord.conf"  # 修改入口命令可能导致沙箱服务失效
#VNC_password =                               # VNC 登录沙箱的密码，不设置则默认为 123456
```

---

### 4️⃣ 运行程序

```bash
cd OpenManus
python sandbox_main.py
```

---

### 5️⃣ 向 Agent 发送任务

你可以通过命令行终端向 Agent 发送任务，Agent 将使用沙箱中的工具来执行你的任务。

---

### 6️⃣ 查看执行结果

* **如果 Agent 使用 `sb_browser_use` 工具：**
  你可以通过 VNC 链接看到浏览器操作。
  VNC 链接会显示在终端输出中，例如：

  ```
  https://6080-sandbox-123456.h7890.daytona.work
  ```

* **如果 Agent 使用 `sb_shell` 工具：**
  你可以在 [Daytona 仪表盘](https://app.daytona.io/dashboard/sandboxes) 中查看沙箱的执行输出。

* **如果 Agent 使用 `sb_files` 工具：**
  它可以在沙箱中创建、读取或修改文件。

---

## 示例

例如，你可以发送以下任务给 Agent：

> “帮我在 [https://hk.trip.com/travel-guide/guidebook/nanjing-9696/?ishideheader=true&isHideNavBar=YES&disableFontScaling=1&catalogId=514634&locale=zh-HK](https://hk.trip.com/travel-guide/guidebook/nanjing-9696/?ishideheader=true&isHideNavBar=YES&disableFontScaling=1&catalogId=514634&locale=zh-HK) 查询相关信息，并制定一份南京旅游攻略，然后保存为 index.html。”

随后你可以：

* 在 VNC 链接（如 `https://6080-sandbox-123456.h7890.proxy.daytona.work`）中看到 Agent 的浏览器操作。
* 在网页地址（如 `https://8080-sandbox-123456.h7890.proxy.daytona.work`）中查看 Agent 生成的 HTML 页面。

---

## 了解更多

* [Daytona 官方文档](https://www.daytona.io/docs/)
