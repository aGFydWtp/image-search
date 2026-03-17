"""Docker Compose構成の検証テスト。YAMLパースと構造チェック。"""

from pathlib import Path

import yaml


def _load_compose() -> dict:
    compose_path = Path(__file__).parent.parent / "docker-compose.yml"
    with open(compose_path) as f:
        return yaml.safe_load(f)


class TestDockerComposeStructure:
    def test_compose_file_exists(self) -> None:
        compose_path = Path(__file__).parent.parent / "docker-compose.yml"
        assert compose_path.exists()

    def test_all_services_defined(self) -> None:
        config = _load_compose()
        services = set(config["services"].keys())
        assert {"qdrant", "ingestion", "search"} == services

    def test_qdrant_uses_official_image(self) -> None:
        config = _load_compose()
        qdrant = config["services"]["qdrant"]
        assert "qdrant/qdrant" in qdrant["image"]

    def test_qdrant_has_named_volume(self) -> None:
        config = _load_compose()
        qdrant = config["services"]["qdrant"]
        volumes = qdrant.get("volumes", [])
        assert any("qdrant_data" in v for v in volumes)
        assert "qdrant_data" in config.get("volumes", {})

    def test_qdrant_has_healthcheck(self) -> None:
        config = _load_compose()
        qdrant = config["services"]["qdrant"]
        assert "healthcheck" in qdrant

    def test_services_depend_on_qdrant(self) -> None:
        config = _load_compose()
        for svc_name in ["ingestion", "search"]:
            svc = config["services"][svc_name]
            depends = svc.get("depends_on", {})
            assert "qdrant" in depends

    def test_host_docker_internal_configured(self) -> None:
        config = _load_compose()
        for svc_name in ["ingestion", "search"]:
            svc = config["services"][svc_name]
            extra_hosts = svc.get("extra_hosts", [])
            assert any("host.docker.internal" in h for h in extra_hosts)

    def test_search_exposes_port_8000(self) -> None:
        config = _load_compose()
        search = config["services"]["search"]
        ports = search.get("ports", [])
        assert any("8000" in str(p) for p in ports)

    def test_ingestion_env_has_ml_endpoints(self) -> None:
        config = _load_compose()
        env = config["services"]["ingestion"]["environment"]
        assert "LM_STUDIO_URL" in env
        assert "EMBEDDING_SERVICE_URL" in env

    def test_ingestion_env_has_qdrant_config(self) -> None:
        config = _load_compose()
        env = config["services"]["ingestion"]["environment"]
        assert env["QDRANT_HOST"] == "qdrant"
        assert env["QDRANT_PORT"] == 6333
