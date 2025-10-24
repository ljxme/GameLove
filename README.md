# 🎮 GameLove

[![网络连通性（TLS 成功率）](scripts/connectivity/connectivity_badge.svg)](scripts/connectivity/CONNECTIVITY.md)
[![License](https://img.shields.io/github/license/artemisia1107/GameLove)](LICENSE)[![Python](https://img.shields.io/badge/python-3.11-blue)](https://www.python.org/downloads/release/python-3110/)[![Update Hosts CI](https://img.shields.io/github/actions/workflow/status/artemisia1107/GameLove/update.yml?branch=main&label=Update%20Hosts)](https://github.com/artemisia1107/GameLove/actions/workflows/update.yml)
[![Latest Release](https://img.shields.io/github/v/release/artemisia1107/GameLove)](https://github.com/artemisia1107/GameLove/releases/latest)

😘 让你"爱"上游戏，解决访问慢、连接超时的问题。

## 一、介绍

对游戏平台说"爱"太难了：访问慢、下载慢、连接超时。

本项目无需安装任何程序，仅需 5 分钟。

通过修改本地 hosts 文件，试图解决：
- 🚀 游戏平台访问速度慢的问题
- 🎯 游戏下载、更新慢的问题  
- 🔗 游戏平台连接超时的问题

让你"爱"上游戏。

**注：** 本项目参考 [GitHub520](https://github.com/521xueweihan/GitHub520) 设计，专注于游戏平台网络优化。

## 二、使用方法

下面的地址无需访问 GitHub 即可获取到最新的 hosts 内容：

- **文件：** `https://raw.githubusercontent.com/artemisia1107/GameLove/refs/heads/main/hosts`
- **JSON：** `https://raw.githubusercontent.com/artemisia1107/GameLove/refs/heads/main/hosts.json`

### 2.1 手动方式

#### 2.1.1 复制下面的内容

```
# GameLove Host Start
23.59.200.146              steamcommunity.com
104.89.226.113             www.steamcommunity.com
23.45.137.115              store.steampowered.com
23.59.200.146              api.steampowered.com
23.56.109.208              steamcdn-a.akamaihd.net
23.192.228.5               cdn.akamai.steamstatic.com
23.192.228.15              community.akamai.steamstatic.com
23.192.228.18              store.akamai.steamstatic.com
23.192.228.20              cdn.cloudflare.steamstatic.com
104.89.226.113             steam-chat.com
104.18.13.27               launcher-public-service-prod06.ol.epicgames.com
44.199.131.83              epicgames.com
3.220.39.146               unrealengine.com
35.169.98.167              fortnite.com
104.18.2.180               easyanticheat.net
23.38.229.240              origin.com
23.37.16.177               ea.com
23.46.216.70               eaassets-a.akamaihd.net
99.84.215.102              ubisoft.com
54.80.124.129              ubi.com
3.248.153.37               uplay.com
96.16.69.97                static3.cdn.ubi.com
166.117.214.166            battle.net
166.117.214.166            blizzard.com
120.55.44.14               battlenet.com.cn
151.101.193.55             gog.com
77.79.249.231              gogalaxy.com
23.203.226.101             rockstargames.com
104.255.105.71             socialclub.rockstargames.com
# Update time: 2025-10-25 00:30:29
# Update url: https://raw.githubusercontent.com/artemisia1107/GameLove/refs/heads/main/hosts
# Star me: https://github.com/artemisia1107/GameLove
# GameLove Host End
```

该内容会自动定时更新，数据更新时间：2025-10-25 00:30:29

> Tips：根目录 `hosts`、`hosts.json`、`scripts/hosts/*` 以及 `scripts/connectivity/*` 均仅由 CI 自动更新。请勿手动修改或在 PR 中更改这些文件，以免与自动更新产生冲突。若需触发即时更新，请在 Actions 中手动运行 `Update GameLove Hosts` 工作流。

#### 2.1.2 修改 hosts 文件

hosts 文件在每个系统的位置不一，详情如下：

- **Windows 系统：** `C:\Windows\System32\drivers\etc\hosts`
- **Linux 系统：** `/etc/hosts`
- **Mac（苹果电脑）系统：** `/etc/hosts`
- **Android（安卓）系统：** `/system/etc/hosts`
- **iPhone（iOS）系统：** `/etc/hosts`

修改方法，把第一步的内容复制到文本末尾：

- **Windows** 使用记事本。
- **Linux、Mac** 使用 Root 权限：`sudo vi /etc/hosts`。
- **iPhone、iPad** 须越狱、**Android** 必须要 root。

#### 2.1.3 激活生效

大部分情况下是直接生效，如未生效可尝试下面的办法，刷新 DNS：

- **Windows：** 在 CMD 窗口输入：`ipconfig /flushdns`
- **Linux** 命令：`sudo nscd restart`，如报错则须安装：`sudo apt install nscd` 或 `sudo /etc/init.d/nscd restart`
- **Mac** 命令：`sudo killall -HUP mDNSResponder`

**Tips：** 上述方法无效可以尝试重启机器。

### 2.2 自动方式（SwitchHosts）

**Tip：** 推荐 [SwitchHosts](https://github.com/oldj/SwitchHosts) 工具管理 hosts
以 SwitchHosts 为例，看一下怎么使用的，配置参考下面：

- **Hosts 类型:** Remote
- **Hosts 标题:** 随意
- **URL:** `https://raw.githubusercontent.com/artemisia1107/GameLove/refs/heads/main/hosts`
- **自动刷新:** 最好选 1 小时

这样每次 hosts 有更新都能及时进行更新，免去手动更新。

### 2.3 一行命令

#### Windows
使用命令需要安装 git bash

复制以下命令保存到本地命名为 `fetch_gamelove_hosts`：

```bash
_hosts=$(mktemp /tmp/hostsXXX)
hosts=/c/Windows/System32/drivers/etc/hosts
remote=https://raw.githubusercontent.com/artemisia1107/GameLove/refs/heads/main/hosts
reg='/# GameLove Host Start/,/# GameLove Host End/d'

sed "$reg" $hosts > "$_hosts"
curl "$remote" >> "$_hosts"
cat "$_hosts" > "$hosts"

rm "$_hosts"
```

在CMD中执行以下命令，执行前需要替换 `git-bash.exe` 和 `fetch_gamelove_hosts` 为你本地的路径，注意前者为windows路径：

```cmd
"C:\Program Files\Git\bin\git-bash.exe" fetch_gamelove_hosts
```

## 三、支持的游戏平台

| 平台 | 域名数量 | 主要解决问题 |
|------|----------|--------------|
| 🎮 **Steam** | 7个域名 | 商店访问、社区加载、下载加速 |
| 🎯 **Epic Games** | 5个域名 | 启动器连接、游戏下载、反作弊 |
| 🎪 **Origin (EA)** | 4个域名 | 平台访问、游戏下载、资源加载 |
| 🎨 **Uplay (Ubisoft)** | 4个域名 | 启动器连接、游戏更新、CDN加速 |
| ⚔️ **Battle.net** | 4个域名 | 暴雪游戏、国服连接、静态资源 |
| 🎲 **GOG** | 3个域名 | 无DRM游戏、Galaxy客户端 |
| 🌟 **Rockstar** | 2个域名 | GTA、荒野大镖客、社交俱乐部 |

## 四、平台专用 hosts

如果你只想优化特定平台，可以使用平台专用的 hosts 文件：

- **Steam：** `https://raw.githubusercontent.com/artemisia1107/GameLove/refs/heads/main/scripts/hosts/hosts_steam`
- **Epic Games：** `https://raw.githubusercontent.com/artemisia1107/GameLove/refs/heads/main/scripts/hosts/hosts_epic`
- **Origin：** `https://raw.githubusercontent.com/artemisia1107/GameLove/refs/heads/main/scripts/hosts/hosts_origin`
- **Uplay：** `https://raw.githubusercontent.com/artemisia1107/GameLove/refs/heads/main/scripts/hosts/hosts_uplay`
- **Battle.net：** `https://raw.githubusercontent.com/artemisia1107/GameLove/refs/heads/main/scripts/hosts/hosts_battle.net`
- **GOG：** `https://raw.githubusercontent.com/artemisia1107/GameLove/refs/heads/main/scripts/hosts/hosts_gog`
- **Rockstar：** `https://raw.githubusercontent.com/artemisia1107/GameLove/refs/heads/main/scripts/hosts/hosts_rockstar`

## 五、自动更新

本项目每1小时自动更新1次，确保 IP 地址的时效性。

你也可以通过以下方式获取更新通知：

1. **Watch** 本项目，选择 "Releases only"
2. 使用 SwitchHosts 设置自动刷新
3. 定期手动检查更新

### 质量指标汇总
- 平均可达性评分：0.965
- 平均共识值：1.000
- 数据更新时间：2025-10-02T11:19:47+08:00
## 六、常见问题

### Q: 为什么有些游戏还是很慢？
A: hosts 文件主要解决 DNS 解析问题，如果你的网络本身较慢或游戏服务器距离较远，可能需要配合加速器使用。

### Q: 会不会影响其他网站访问？
A: 不会。本项目只针对游戏平台域名进行优化，不会影响其他网站的正常访问。

### Q: 如何恢复原始 hosts 文件？
A: 删除 `# GameLove Host Start` 到 `# GameLove Host End` 之间的所有内容即可。

### Q: 支持添加新的游戏平台吗？
A: 当然！欢迎提交 Issue 或 Pull Request 添加新的游戏平台支持。

## 七、贡献指南

欢迎贡献代码！请遵循以下步骤：

1. Fork 本项目
2. 创建你的特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交你的修改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开一个 Pull Request

## 八、免责声明

- 本项目仅供学习和研究使用
- 请遵守当地法律法规和游戏平台服务条款
- 使用本项目产生的任何问题，作者不承担责任

## 九、许可证

本项目采用 [MIT 许可证](LICENSE)。

## 十、致谢

- 感谢 [GitHub520](https://github.com/521xueweihan/GitHub520) 项目的设计灵感
- 感谢所有贡献者的支持

## 十一、Star History

[![Star History Chart](https://api.star-history.com/svg?repos=artemisia1107/GameLove&type=Date)](https://star-history.com/#artemisia1107/GameLove&Date)

---

如果这个项目对你有帮助，请给个 ⭐ Star 支持一下！

让我们一起"爱"上游戏！🎮
