import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


def _load_module():
    project_root = Path(__file__).resolve().parents[1]
    script_path = project_root / "scripts" / "py_scripts" / "migrate_yaml_prompts_to_db.py"
    spec = importlib.util.spec_from_file_location("migrate_yaml_prompts_to_db", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_infer_pipeline_id_falls_back_to_filename():
    module = _load_module()
    conf = SimpleNamespace(
        pipeline_id=None,
        graph_config=SimpleNamespace(pipeline_id=None),
    )
    out = module._infer_pipeline_id(conf, "/tmp/blueberry.yaml")
    assert out == "blueberry"


def test_extract_prompt_dict_for_react_txt(tmp_path):
    module = _load_module()
    prompt_f = tmp_path / "sys.txt"
    prompt_f.write_text("hello react", encoding="utf-8")
    graph_conf = SimpleNamespace(sys_prompt_f=str(prompt_f))
    prompt_dict = module._extract_prompt_dict(graph_conf)
    assert prompt_dict == {"sys_prompt": "hello react"}


def test_extract_prompt_dict_for_routing_dir(tmp_path):
    module = _load_module()
    (tmp_path / "route_prompt.txt").write_text("route", encoding="utf-8")
    (tmp_path / "chat_prompt.txt").write_text("chat", encoding="utf-8")
    graph_conf = SimpleNamespace(sys_promp_dir=str(tmp_path))
    prompt_dict = module._extract_prompt_dict(graph_conf)
    assert prompt_dict["route_prompt"] == "route"
    assert prompt_dict["chat_prompt"] == "chat"


def test_collect_payload_routing_ignores_chatty_prompt_for_tool_node(tmp_path):
    module = _load_module()
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "route_prompt.txt").write_text("route", encoding="utf-8")
    (prompt_dir / "chat_prompt.txt").write_text("chat", encoding="utf-8")
    (prompt_dir / "tool_prompt.txt").write_text("tool", encoding="utf-8")
    (prompt_dir / "chatty_prompt.txt").write_text("chatty", encoding="utf-8")

    class RoutingConfig:
        pass

    class ToolNodeConfig:
        pass

    graph_conf = RoutingConfig()
    graph_conf.sys_promp_dir = str(prompt_dir)
    graph_conf.tool_node_config = ToolNodeConfig()
    graph_conf.tool_node_config.tool_prompt_f = str(prompt_dir / "tool_prompt.txt")

    conf = SimpleNamespace(
        pipeline_id=None,
        api_key="sk",
        graph_config=graph_conf,
    )

    module.load_tyro_conf = lambda _: conf
    payload = module._collect_payload(str(tmp_path / "xiaozhan.yaml"))
    assert payload.pipeline_id == "xiaozhan"
    assert set(payload.prompt_dict.keys()) == {"route_prompt", "chat_prompt", "tool_prompt"}
    assert "chatty_prompt" not in payload.prompt_dict


def test_collect_payload_routing_includes_chatty_prompt_for_chatty_node(tmp_path):
    module = _load_module()
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "route_prompt.txt").write_text("route", encoding="utf-8")
    (prompt_dir / "chat_prompt.txt").write_text("chat", encoding="utf-8")
    (prompt_dir / "tool_prompt.txt").write_text("tool", encoding="utf-8")
    (prompt_dir / "chatty_prompt.txt").write_text("chatty", encoding="utf-8")

    class RoutingConfig:
        pass

    class ChattyToolNodeConfig:
        pass

    graph_conf = RoutingConfig()
    graph_conf.sys_promp_dir = str(prompt_dir)
    graph_conf.tool_node_config = ChattyToolNodeConfig()
    graph_conf.tool_node_config.tool_prompt_f = str(prompt_dir / "tool_prompt.txt")
    graph_conf.tool_node_config.chatty_sys_prompt_f = str(
        prompt_dir / "chatty_prompt.txt"
    )

    conf = SimpleNamespace(
        pipeline_id="xiaozhan",
        api_key="sk",
        graph_config=graph_conf,
    )

    module.load_tyro_conf = lambda _: conf
    payload = module._collect_payload(str(tmp_path / "xiaozhan.yaml"))
    assert payload.pipeline_id == "xiaozhan"
    assert "chatty_prompt" in payload.prompt_dict

