import logging

from django.apps import AppConfig

log = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    name = "core"

    def ready(self) -> None:
        from shopfinder import __version__

        log.info("shop-finder-api %s", __version__)
