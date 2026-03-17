"""Ingestion Service エントリポイント（バッチ実行用）。"""

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("Ingestion pipeline started")
    logger.info("Ingestion pipeline finished (no tasks implemented yet)")


if __name__ == "__main__":
    main()
