"""Tests for backup API endpoints."""
import pytest
from fastapi.testclient import TestClient


class TestBackupEndpoints:
    """Test backup API endpoints."""

    def test_get_backup_status(self, client: TestClient):
        """Test getting backup status."""
        response = client.get("/api/backups/stats")
        assert response.status_code in [200, 404]

    def test_create_backup(self, client: TestClient):
        """Test creating a backup."""
        response = client.post("/api/backups", json={"backup_type": "full"})
        assert response.status_code in [200, 201]

    def test_list_backups(self, client: TestClient):
        """Test listing backups."""
        response = client.get("/api/backups")
        assert response.status_code == 200

    def test_restore_backup_not_found(self, client: TestClient):
        """Test restoring a non-existent backup."""
        response = client.post("/api/backups/non-existent-backup-12345/restore")
        assert response.status_code == 404

    def test_delete_backup_not_found(self, client: TestClient):
        """Test deleting a non-existent backup."""
        response = client.delete("/api/backups/non-existent-backup-12345")
        assert response.status_code == 404


class TestBackupValidation:
    """Test backup validation."""

    def test_create_backup_with_options(self, client: TestClient):
        """Test creating backup with options."""
        response = client.post(
            "/api/backups",
            json={
                "backup_type": "full",
                "description": "Test backup with description",
            }
        )
        assert response.status_code in [200, 201]
