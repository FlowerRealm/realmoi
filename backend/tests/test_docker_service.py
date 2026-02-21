from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

from docker.errors import ImageNotFound

from backend.app.services import docker_service


@dataclass
class FakeImages:
    existing: set[str] = field(default_factory=set)
    get_calls: list[str] = field(default_factory=list)
    pull_calls: list[str] = field(default_factory=list)

    def get_image(self, image: str) -> object:
        self.get_calls.append(image)
        if image in self.existing:
            return object()
        raise ImageNotFound("not found")

    get = get_image

    def pull(self, image: str) -> object:
        self.pull_calls.append(image)
        self.existing.add(image)
        return object()

def make_client(*, existing: set[str] | None = None):
    images = FakeImages(existing=set(existing or set()))
    return SimpleNamespace(images=images)


def setup_function() -> None:
    _ = docker_service._READY_IMAGES.clear()  # noqa: SLF001


def test_ensure_image_ready_pull_once() -> None:
    image = "demo/runner:latest"
    client = make_client()

    docker_service.ensure_image_ready(client=client, image=image)
    docker_service.ensure_image_ready(client=client, image=image)

    assert client.images.get_calls == [image]
    assert client.images.pull_calls == [image]


def test_ensure_image_ready_uses_local_image() -> None:
    image = "demo/runner:local"
    client = make_client(existing={image})

    docker_service.ensure_image_ready(client=client, image=image)

    assert client.images.get_calls == [image]
    assert client.images.pull_calls == []
