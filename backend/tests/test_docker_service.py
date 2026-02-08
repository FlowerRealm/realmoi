from __future__ import annotations

from docker.errors import ImageNotFound

from backend.app.services import docker_service


class _FakeImages:
    def __init__(self, existing: set[str] | None = None) -> None:
        self.existing = set(existing or set())
        self.get_calls: list[str] = []
        self.pull_calls: list[str] = []

    def get(self, image: str) -> object:
        self.get_calls.append(image)
        if image in self.existing:
            return object()
        raise ImageNotFound("not found")

    def pull(self, image: str) -> object:
        self.pull_calls.append(image)
        self.existing.add(image)
        return object()


class _FakeClient:
    def __init__(self, existing: set[str] | None = None) -> None:
        self.images = _FakeImages(existing)


def setup_function() -> None:
    docker_service._READY_IMAGES.clear()  # noqa: SLF001


def test_ensure_image_ready_pull_once() -> None:
    image = "demo/runner:latest"
    client = _FakeClient()

    docker_service.ensure_image_ready(client=client, image=image)
    docker_service.ensure_image_ready(client=client, image=image)

    assert client.images.get_calls == [image]
    assert client.images.pull_calls == [image]


def test_ensure_image_ready_uses_local_image() -> None:
    image = "demo/runner:local"
    client = _FakeClient(existing={image})

    docker_service.ensure_image_ready(client=client, image=image)

    assert client.images.get_calls == [image]
    assert client.images.pull_calls == []
