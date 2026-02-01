from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class BatchDecayResult:
    total: int
    updated: int
    failed: int
    details: List[Dict]


class DecayBatchProcessor:
    def __init__(self, memory_manager, decay_calculator):
        self.memory_manager = memory_manager
        self.decay_calculator = decay_calculator
        self._batch_size = 100

    async def process_batch(
        self,
        batch_size: int = 100,
        sync: bool = False,
        dry_run: bool = False
    ) -> BatchDecayResult:
        if batch_size > 0:
            self._batch_size = batch_size

        memories = self.memory_manager.search_memories(
            limit=self._batch_size,
            filters={"archived": False}
        )

        if not memories:
            return BatchDecayResult(
                total=0,
                updated=0,
                failed=0,
                details=[]
            )

        results = []
        updated_count = 0
        failed_count = 0

        for memory in memories:
            memory_id = memory["id"]
            try:
                decayed_value = self.decay_calculator.calculate_decay(memory)

                if dry_run:
                    results.append({
                        "memory_id": memory_id,
                        "old_value": memory.get("importance_score", 0.0),
                        "new_value": decayed_value,
                        "dry_run": True
                    })
                    updated_count += 1
                else:
                    success = self.memory_manager.update_memory(
                        memory_id=memory_id,
                        new_importance_score=decayed_value
                    )

                    if success:
                        results.append({
                            "memory_id": memory_id,
                            "old_value": memory.get("importance_score", 0.0),
                            "new_value": decayed_value,
                            "updated": True
                        })
                        updated_count += 1
                    else:
                        results.append({
                            "memory_id": memory_id,
                            "error": "Update failed",
                            "updated": False
                        })
                        failed_count += 1
            except Exception as e:
                logger.error(f"处理记忆失败: {memory_id}, {e}")
                results.append({
                    "memory_id": memory_id,
                    "error": str(e),
                    "updated": False
                })
                failed_count += 1

        if sync and not dry_run:
            sync_result = self.memory_manager.sync_decay_values()
            logger.info(f"同步衰减值: 更新={sync_result['updated']}, 失败={sync_result['failed']}")

        return BatchDecayResult(
            total=len(memories),
            updated=updated_count,
            failed=failed_count,
            details=results
        )

    async def process_all(
        self,
        batch_size: int = 100,
        sync: bool = False,
        dry_run: bool = False
    ) -> Dict:
        total_updated = 0
        total_failed = 0
        all_details = []
        batch_count = 0

        while True:
            batch_result = await self.process_batch(
                batch_size=batch_size,
                sync=False,
                dry_run=dry_run
            )

            batch_count += 1
            total_updated += batch_result.updated
            total_failed += batch_result.failed
            all_details.extend(batch_result.details)

            logger.info(
                f"批次 {batch_count}: 总数={batch_result.total}, "
                f"更新={batch_result.updated}, 失败={batch_result.failed}"
            )

            if batch_result.total < batch_size:
                break

        if sync and not dry_run:
            sync_result = self.memory_manager.sync_decay_values()
            logger.info(f"同步衰减值: 更新={sync_result['updated']}, 失败={sync_result['failed']}")

        return {
            "total_batches": batch_count,
            "total_updated": total_updated,
            "total_failed": total_failed,
            "details": all_details
        }

    def get_batch_status(self) -> Dict:
        return {
            "batch_size": self._batch_size,
            "memory_manager": self.memory_manager is not None,
            "decay_calculator": self.decay_calculator is not None
        }
