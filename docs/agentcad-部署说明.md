# CAD Skill 隔离运行时部署说明

`cad-agentcad` 不在 API 服务宿主机直接执行模型生成的 Python。它使用平台统一
的 Skill Runtime：会话独立 Workspace、服务端命令策略、无网络容器沙箱和
基于 Artifact ID 的产物访问。

## 构建运行时

需要 Docker（也可通过 `SKILL_SANDBOX_ENGINE` 指定兼容引擎）：

```bash
bash setup_agentcad.sh
```

脚本从 `docker/agentcad/Dockerfile` 构建
`agent-platform/agentcad:0.4.0`。镜像中的 agentcad 固定为 `0.4.0`，避免
上游非兼容更新影响平台。生产部署应在 CI 构建镜像并推送到内部镜像仓库，
然后把 `CAD_RUNTIME_IMAGE` 配置为不可变 digest。

## 关键配置

```dotenv
SKILL_SANDBOX_ENGINE=docker
SKILL_WORKSPACE_ROOT=.agent-platform/workspaces
SKILL_ARTIFACT_ROOT=.agent-platform/artifacts
CAD_SKILL_ENABLED=true
CAD_RUNTIME_IMAGE=agent-platform/agentcad:0.4.0
CAD_RUNTIME_TIMEOUT_SECONDS=300
CAD_RUNTIME_MEMORY_MB=2048
CAD_RUNTIME_CPUS=2.0
CAD_RUNTIME_PIDS_LIMIT=64
```

Workspace 和 Artifact 根目录需要由 API 进程写入。多 worker 或多实例部署时，
Artifact 根目录必须使用共享持久卷；这样随机 Artifact ID 在进程重启后仍可解析。

## 安全边界

- 容器无网络、只读根文件系统、丢弃全部 Linux capabilities，并启用
  `no-new-privileges`。
- 仅挂载当前 Skill/会话的 Workspace，设置 CPU、内存、进程数和执行超时。
- Runtime Profile 只批准 `agentcad` 的有限子命令和镜像内置 viewer helper。
- CAD `.py` 只能经 `workspace_write` 写入隔离目录；通用 `write_file` 不再接受
  `.py`/`.pyw`。
- HTML 通过 `publish_artifact` 发布，接口设置 CSP、`nosniff`，前端 iframe
  继续使用 `sandbox="allow-scripts"`。

## 就绪检查

`GET /skills` 会验证容器引擎及镜像是否存在。未就绪时 CAD Skill 标记为
`ready=false`，显式请求会安全降级为通用对话。可用以下命令检查镜像：

```bash
docker image inspect agent-platform/agentcad:0.4.0
```

## 新增其他可执行 Skill

不要把命令加入全局 `bash` 白名单。应在 `SkillRuntimeManager` 注册新的
Runtime Profile，明确镜像、允许命令、可写扩展名、网络策略和资源上限；Skill
frontmatter 通过 `runtime` 引用该 Profile，并使用 Workspace/Sandbox/Artifact
工具。这样每个 Skill 的权限互不扩散。
