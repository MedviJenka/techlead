import asyncio
import json
import uuid
from pathlib import Path

from httpx import AsyncClient

from tests.platform.conftest import as_user


async def business_path(
    client: AsyncClient, prefix: str, slug: str = "test", headers: dict[str, str] | None = None
) -> str:
    response = await client.post(f"{prefix}/businesses", json={"name": slug, "slug": slug}, headers=headers)
    assert response.status_code == 201
    return f"{prefix}/businesses/{response.json()['id']}"


async def test_sample_import_replay_and_dashboard(client: AsyncClient, api_prefix: str) -> None:
    path = await business_path(client, api_prefix)
    sample = json.loads((Path(__file__).parents[2] / "docs/files/sample_raw_leads.json").read_text())
    count = len(sample["leads"])
    imported = await client.post(f"{path}/leads/import", json=sample)
    assert imported.status_code == 200, imported.text
    assert imported.json()["created"] == count
    assert imported.json()["failed"] == 0
    replay = await client.post(f"{path}/leads/import", json=sample)
    assert replay.json()["skipped"] == count
    lead_id = imported.json()["results"][0]["lead_id"]
    timeline = (await client.get(f"{path}/leads/{lead_id}/activities")).json()
    assert timeline["total"] == 1
    assert timeline["items"][0]["metadata"]["imported"] is True
    listing = (await client.get(f"{path}/leads?limit=2")).json()
    assert listing["total"] == count and len(listing["items"]) == 2
    assert "raw_payload" not in listing["items"][0]
    details = (await client.get(f"{path}/leads/{lead_id}")).json()
    assert details["first_name"] == "Daniel" and details["lead_score"] == 92
    assert "raw_payload" not in details
    dashboard = await client.get(f"{path}/dashboard")
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["counts"]["total"] == count
    assert dashboard.json()["counts"]["waiting_for_proposal"] == 1
    assert sum(bucket["count"] for bucket in dashboard.json()["by_score"]) == count


async def test_partial_import_merge_patch_and_tenant_isolation(client: AsyncClient, api_prefix: str) -> None:
    path = await business_path(client, api_prefix)
    other_user = as_user(uuid.uuid4())
    other = await business_path(client, api_prefix, "other", other_user)
    record = {
        "lead_id": "one",
        "source": "Website Form",
        "contact": {"email": " TEST@example.com "},
        "status": "qualified",
        "custom_fields": {"keep": 1},
    }
    response = await client.post(f"{path}/leads/import", json={"leads": [record, {"source": ""}]})
    assert response.json()["created"] == 1 and response.json()["failed"] == 1
    lead_id = response.json()["results"][0]["lead_id"]
    assert response.json()["results"][1]["errors"][0]["loc"] == ["source"]
    merge = await client.post(
        f"{path}/leads",
        json={"source": "email", "email": "test@example.com", "first_name": "Test", "custom_fields": {"add": 2}},
    )
    assert merge.status_code == 200, merge.text
    assert merge.json()["id"] == lead_id and merge.json()["status"] == "qualified"
    assert merge.json()["custom_fields"] == {"keep": 1, "add": 2}
    patch = await client.patch(f"{path}/leads/{lead_id}", json={"status": "won", "notes": None, "custom_fields": {}})
    assert patch.status_code == 200, patch.text
    assert patch.json()["status"] == "won" and patch.json()["custom_fields"] == {}
    timeline = (await client.get(f"{path}/leads/{lead_id}/activities")).json()
    status_events = [row for row in timeline["items"] if row["activity_type"] == "status_changed"]
    assert len(status_events) == 1 and status_events[0]["metadata"] == {"from": "qualified", "to": "won"}
    await client.patch(f"{path}/leads/{lead_id}", json={"status": "won"})
    assert (await client.get(f"{path}/leads/{lead_id}/activities")).json()["total"] == timeline["total"]
    # Another business's member never sees this business's leads, even through their own business's routes.
    for suffix in (f"/leads/{lead_id}", f"/leads/{lead_id}/activities"):
        assert (await client.get(other + suffix, headers=other_user)).status_code == 404
    patch_other = await client.patch(f"{other}/leads/{lead_id}", json={"status": "lost"}, headers=other_user)
    assert patch_other.status_code == 404
    assert (await client.get(f"{other}/leads", headers=other_user)).json()["total"] == 0
    assert (await client.get(f"{other}/dashboard", headers=other_user)).json()["counts"]["total"] == 0
    imported = await client.post(f"{other}/leads/import", json={"leads": [record]}, headers=other_user)
    assert imported.json()["created"] == 1
    # And neither user can open the other's business at all.
    for business, headers in ((other, None), (path, other_user)):
        for suffix in ("", "/leads", f"/leads/{lead_id}", "/dashboard"):
            assert (await client.get(business + suffix, headers=headers)).status_code == 404


async def test_concurrent_contact_deduplication(client: AsyncClient, api_prefix: str) -> None:
    path = await business_path(client, api_prefix)
    responses = await asyncio.gather(
        *[client.post(f"{path}/leads", json={"source": "web", "email": "same@example.com"}) for _ in range(4)]
    )
    assert all(response.status_code == 200 for response in responses)
    assert len({response.json()["id"] for response in responses}) == 1
    lead_id = responses[0].json()["id"]
    assert (await client.get(f"{path}/leads/{lead_id}/activities")).json()["total"] == 1


async def test_filters_validation_and_missing_business(client: AsyncClient, api_prefix: str) -> None:
    path = await business_path(client, api_prefix)
    for name in ("100% Match", "Other"):
        await client.post(f"{path}/leads", json={"source": "Web Form", "first_name": name, "priority": "HIGH"})
    found = await client.get(f"{path}/leads", params={"q": "%", "source": "web form", "priority": "high"})
    assert found.status_code == 200, found.text
    assert found.json()["total"] == 1
    lead_id = found.json()["items"][0]["id"]
    for query in ("limit=101", "offset=-1", "priority=urgent", "unexpected=true"):
        assert (await client.get(f"{path}/leads?{query}")).status_code == 422
    assert (await client.patch(f"{path}/leads/{lead_id}", json={"status": None})).status_code == 422
    assert (await client.patch(f"{path}/leads/{lead_id}", json={"lead_score": 99})).status_code == 422
    missing = f"{api_prefix}/businesses/{uuid.uuid4()}"
    for suffix in ("/leads", "/dashboard"):
        assert (await client.get(missing + suffix)).status_code == 404
    assert (await client.post(f"{missing}/leads/import", json={"leads": [{"source": "web"}]})).status_code == 404


async def test_dedup_precedence_phone_and_score_history(client: AsyncClient, api_prefix: str) -> None:
    path = await business_path(client, api_prefix)
    first = (
        await client.post(
            f"{path}/leads",
            json={
                "source": "web",
                "external_id": "one",
                "email": "first@example.com",
                "phone": "+1234567890",
            },
        )
    ).json()
    second = (
        await client.post(
            f"{path}/leads",
            json={
                "source": "web",
                "external_id": "two",
                "email": "second@example.com",
                "phone": "+1987654321",
            },
        )
    ).json()
    # Email takes precedence over phone when they point to different leads.
    email_match = await client.post(
        f"{path}/leads",
        json={
            "source": "email",
            "email": "first@example.com",
            "phone": "+1987654321",
        },
    )
    assert email_match.json()["id"] == first["id"]
    # The source identity takes precedence over a conflicting email match.
    external_match = await client.post(
        f"{path}/leads",
        json={
            "source": "web",
            "external_id": "two",
            "email": "first@example.com",
            "phone": "+1111111111",
        },
    )
    assert external_match.json()["id"] == second["id"]
    phone_match = await client.post(f"{path}/leads", json={"source": "phone", "phone": "+1111111111"})
    assert phone_match.json()["id"] == second["id"]
    score = await client.post(
        f"{path}/leads/import",
        json={
            "leads": [
                {
                    "source": "web",
                    "lead_id": "two",
                    "ai": {"lead_score": 85},
                }
            ]
        },
    )
    assert score.json()["updated"] == 1
    timeline = (await client.get(f"{path}/leads/{second['id']}/activities")).json()
    changes = [row for row in timeline["items"] if row["activity_type"] == "score_changed"]
    assert len(changes) == 1 and changes[0]["metadata"] == {"from": None, "to": 85}
