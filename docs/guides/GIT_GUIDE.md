# Soil-SCM Git 操作备忘

> 本备忘记录本项目 Git 推送、Token 管理与版本发布的完整流程，方便下次直接调用。

## 1. 仓库信息

| 项目 | 值 |
|------|-----|
| 远程仓库 | `https://github.com/YYC-JNU/Soil-SCM.git` |
| 默认分支 | `main` |
| 当前版本 | `v0.1.0`（tag `v0.1.0`，首次提交 `492be5b`） |

## 2. 日常推送（推荐命令）

```powershell
# 推送代码
git -c credential.helper=store push origin main

# 推送标签
git -c credential.helper=store push origin v0.1.0
```

> **注意**：本机系统级 Git Credential Manager 会干扰认证，推送时**必须带** `-c credential.helper=store` 参数。Token 已存入 `~/.git-credentials`，无需重复输入。
>
> **⚠️ 推送确认约定（2026-08-11 起）**：**所有 `git push` 操作前，必须先征得项目负责人明确确认，确认后才可推送。** 本地 `git add` / `git commit` 无需确认，仅 `git push` 需要。

## 3. Token 管理

| 项目 | 值 |
|------|-----|
| 存储位置 | `~/.git-credentials`（用户主目录） |
| 存储格式 | `https://<用户名>:<TOKEN>@github.com` |
| Token 类型 | Fine-grained PAT（`github_pat_` 开头） |
| 权限要求 | Repository access = `Soil-SCM`；Repository permissions → **Contents: Read and write** |
| 有效期 | 默认 **30 天**，到期后推送报错 |

### 更新 Token 步骤

1. GitHub → **Settings** → **Developer settings** → **Fine-grained personal access tokens**
2. 重新生成/编辑 Token，勾选：
   - Repository access：`Only select repositories` → **Soil-SCM**
   - Permissions → Repository permissions → **Contents: Read and write**
3. 更新本地凭据文件（PowerShell）：

```powershell
Set-Content -Path "~\.git-credentials" -Value "https://<GitHub用户名>:<新TOKEN>@github.com" -NoNewline
```

## 4. 发布新版本流程（示例：v0.2.0）

```powershell
# 1. 修改版本号
#    src/__init__.py 中 __version__ = "0.2.0"
#    README.md 版本信息同步更新

# 2. 暂存并提交
git add -A
git commit -m "feat: 描述本次更新"

# 3. 打标签
git tag -a v0.2.0 -m "Soil-SCM v0.2.0"

# 4. 推送分支与标签
git -c credential.helper=store push origin main
git -c credential.helper=store push origin v0.2.0
```

## 5. 常见问题排查

| 现象 | 原因 | 解决办法 |
|------|------|----------|
| `fatal: Authentication failed` | Token 过期或无效 | 按第 3 节更新 `~/.git-credentials` |
| `403 Permission to ... denied to <GitHub用户名>` | Token 缺 `Contents: Read and write` 权限 | GitHub 上修改 Token 权限并保存 |
| 不加 `-c` 参数时报认证失败 | 系统级 Git Credential Manager 干扰 | 始终使用 `-c credential.helper=store` |
| `non-fast-forward` / push rejected | 远端有他人提交 | `git pull --rebase` 后再推送 |
| `URL rejected: Bad hostname` | Token 提取/变量内插错误 | 直接用 `-c credential.helper=store` 方式推送 |

## 6. 状态检查命令

```powershell
git status -sb                # 工作区与分支跟踪状态
git log --oneline -5          # 最近提交
git tag -l                    # 本地标签列表
git ls-remote origin          # 远端分支与标签
```
