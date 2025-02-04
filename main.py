from pkg.plugin.context import register, handler, BasePlugin, APIHost, EventContext
from pkg.plugin.events import *
from pkg.provider.entities import Message
import yaml
import json
import os

@register(name="贴吧老哥模式/喷子/键盘侠", description="模拟贴吧老哥的喷人方式有温和版和暴躁版，可以自由开关", version="0.1", author="小馄饨")
class TiebaModePlugin(BasePlugin):
    enabled_users = set()
    prompt_template = []
    config = {}

    def __init__(self, host: APIHost):
        self.host = host

    async def initialize(self):
        # 读取配置文件
        config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f)
        except Exception as e:
            print(f"读取配置文件失败: {e}")
            return

        # 初始化模板路径
        self.templates = {
            "暴躁": os.path.join(os.path.dirname(__file__), "暴躁.json"),
            "温和": os.path.join(os.path.dirname(__file__), "温和.json")
        }

    # 处理个人消息命令
    @handler(PersonNormalMessageReceived)
    async def handle_person_command(self, ctx: EventContext):
        await self.handle_command(ctx)

    # 处理群消息命令
    @handler(GroupNormalMessageReceived)
    async def handle_group_command(self, ctx: EventContext):
        await self.handle_command(ctx)

    # 通用命令处理逻辑
    async def handle_command(self, ctx: EventContext):
        msg = ctx.event.text_message.lower()  # 转换为小写
        user_id = ctx.event.sender_id
        is_group = isinstance(ctx.event, GroupNormalMessageReceived)

        if msg == "/贴吧帮助":
            help_text = [
                "贴吧模式使用说明：",
                "1. 基础命令：",
                "   • /开启贴吧模式 [风格] - 开启贴吧模式，风格可选：暴躁, 温和， 默认暴躁",
                "   • /关闭贴吧模式 - 关闭贴吧模式",
                "2. 使用示例：",
                "   • /开启贴吧模式 暴躁 - 使用暴躁风格开启",
                "   • /开启贴吧模式 温和 - 使用温和风格开启",
                "   • /关闭贴吧模式 - 关闭贴吧模式",
                "3. 注意事项：",
                "   • 开启后对话将采用贴吧风格",
                "   • 关闭后恢复正常",
                "   • 群聊和私聊均可使用",
                "4. 温馨提示：",
                "   • 命令和风格名称不区分大小写"
            ]
            ctx.add_return("reply", ["\n".join(help_text)])
            ctx.prevent_default()
            return

        elif msg.startswith("/开启贴吧模式"):
            if user_id in self.enabled_users:
                ctx.add_return("reply", ["已经处于贴吧模式"])
                ctx.prevent_default()
                return

            parts = msg.split()
            style = parts[1].lower() if len(parts) > 1 else "暴躁"

            if style not in self.templates:
                ctx.add_return("reply", [f"风格 {style} 不存在，可用风格：暴躁, 温和"])
                ctx.prevent_default()
                return

            try:
                with open(self.templates[style], "r", encoding="utf-8") as f:
                    self.prompt_template = json.load(f)
                    self.enabled_users.add(user_id)
                    chat_type = "群聊" if is_group else "私聊"
                    ctx.add_return("reply", [f"已在{chat_type}开启贴吧模式（{style} 风格）"])
                    ctx.prevent_default()
                    if self.config.get("debug", False):
                        print(f"[贴吧模式] 用户 {user_id} 在{chat_type}开启贴吧模式，风格: {style}")
            except Exception as e:
                ctx.add_return("reply", [f"加载风格失败: {e}"])
                ctx.prevent_default()

        elif msg == "/关闭贴吧模式":
            if user_id in self.enabled_users:
                self.enabled_users.remove(user_id)
                chat_type = "群聊" if is_group else "私聊"
                ctx.add_return("reply", [f"已在{chat_type}关闭贴吧模式"])
                ctx.prevent_default()
                if self.config.get("debug", False):
                    print(f"[贴吧模式] 用户 {user_id} 在{chat_type}关闭贴吧模式")

    # 处理提示词注入
    @handler(PromptPreProcessing)
    async def handle_prompt(self, ctx: EventContext):
        # 检查是否是启用了新模式的用户
        if not hasattr(ctx.event.query, "sender_id") or \
           ctx.event.query.sender_id not in self.enabled_users:
            return

        # 获取当前用户输入
        current_input = ""
        if hasattr(ctx.event.query, "user_message"):
            msg = ctx.event.query.user_message
            if isinstance(msg.content, list) and msg.content and hasattr(msg.content[0], 'text'):
                current_input = msg.content[0].text
            else:
                current_input = str(msg.content)

        # 调试日志 - 记录原始状态
        original_prompt = []
        if self.config.get("debug", False):
            original_prompt = [Message(role=msg.role, content=msg.content) for msg in ctx.event.default_prompt]

        # 构建新的提示词
        new_system_prompt = []
        chat_history = []  # 存储历史对话

        # 从模板中获取所有消息，并在适当位置插入历史对话
        for msg in self.prompt_template:
            if msg["role"] == "system":
                if msg["content"] == "<聊天记录>" and ctx.event.prompt:
                    # 在<聊天记录>标记处插入历史对话
                    for chat_msg in ctx.event.prompt:
                        content = chat_msg.content
                        # 如果内容是 ContentElement 列表，提取 text
                        if isinstance(content, list) and content and hasattr(content[0], 'text'):
                            content = content[0].text
                        chat_history.append(Message(
                            role=chat_msg.role,
                            content=content
                        ))
                new_system_prompt.append(Message(
                    role=msg["role"],
                    content=msg["content"]
                ))
            elif msg["role"] == "assistant" or msg["role"] == "user":
                content = msg["content"]
                # 替换当前输入占位符
                if "<当前输入内容>" in content:
                    content = content.replace("<当前输入内容>", current_input)
                new_system_prompt.append(Message(
                    role=msg["role"],
                    content=content
                ))

        # 添加用户预设内容（在<用户预设>标记后）
        final_prompt = []
        for msg in new_system_prompt:
            final_prompt.append(msg)
            if msg.content == "<用户预设>":
                for preset in ctx.event.default_prompt:
                    final_prompt.append(preset)
            elif msg.content == "<聊天记录>":
                final_prompt.extend(chat_history)

        # 替换默认提示词
        ctx.event.default_prompt.clear()
        ctx.event.default_prompt.extend(final_prompt)

        # 调试日志 - 仅在 debug 模式下输出
        if self.config.get("debug", False):
            print("\n=== 贴吧模式调试信息 ===")
            print(f"用户ID: {ctx.event.query.sender_id}")
            print(f"当前输入: {current_input}")
            print("\n[原始提示词]")
            for msg in original_prompt:
                print(f"  [{msg.role}] {msg.content}")
            print("\n[修改后提示词]")
            for msg in final_prompt:
                print(f"  [{msg.role}] {msg.content}")
            print("=" * 50)

    def __del__(self):
        pass