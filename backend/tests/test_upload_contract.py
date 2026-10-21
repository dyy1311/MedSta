"""019 B1–B4：上传契约（成功/拒绝/脏表/多表工作区）。"""
from __future__ import annotations

import io

import pandas as pd
import pytest

from medsta.session.manager import manager


CSV = "age,city\n25,Beijing\n31,Shanghai\n42,Beijing\n".encode("utf-8")

_DIRTY_CSV = (
    "\ufeff姓名,年龄,得分\n"
    "张三,25,3.1\n"
    "李四,,\n"
    "王五,31,NA\n"
    " ,40,4.0\n"
    "\n"
).encode("utf-8")


def _upload(client, session_id: str, name: str, content: bytes):
    return client.post(
        f"/sessions/{session_id}/data",
        files={"file": (name, io.BytesIO(content), "application/octet-stream")},
    )


def test_upload_csv_returns_profile_and_dataset(client, session_id: str, data_root) -> None:
    """B1: CSV 上传返回画像 + dataset_id，文件落到注入的数据根。"""
    resp = _upload(client, session_id, "cohort.csv", CSV)

    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "data_profile"
    assert body["dataset_id"]
    assert body["profile"]["row_count"] == 3
    assert body["profile"]["column_count"] == 2
    # 整数测量变量（age）按连续处理；评分/分级类小基数整数才判等级型
    assert body["profile"]["columns"]["age"]["type"] == "continuous"
    assert (data_root / session_id / body["dataset_id"] / "dataset.csv").is_file()


def test_upload_xlsx_returns_profile(client, session_id: str, tmp_path) -> None:
    """B1: XLSX 与 CSV 行为一致（扩展名大小写不敏感）。"""
    frame = pd.DataFrame({"age": [25, 31, 42], "city": ["a", "b", "a"]})
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False)
    resp = _upload(client, session_id, "cohort.XLSX", buffer.getvalue())

    assert resp.status_code == 200
    assert resp.json()["profile"]["row_count"] == 3


def test_upload_rejects_unsupported_extension(client, session_id: str) -> None:
    """B2: 不支持的扩展名返回 400，且错误信息说明类型。"""
    resp = _upload(client, session_id, "notes.txt", b"hello")

    assert resp.status_code == 400
    assert "不支持的文件类型" in resp.json()["detail"]


def test_upload_unknown_session_returns_404(client) -> None:
    """B2: 未知会话返回 404，不写入磁盘。"""
    resp = _upload(client, "missing-session", "cohort.csv", CSV)

    assert resp.status_code == 404
    assert "会话不存在" in resp.json()["detail"]


def test_upload_empty_file_returns_400_not_500(client, session_id: str) -> None:
    """B3: 空文件是可分类的 400，而不是服务器异常。"""
    resp = _upload(client, session_id, "empty.csv", b"")

    assert resp.status_code == 400
    assert "解析失败" in resp.json()["detail"] or "为空" in resp.json()["detail"]


def test_upload_dirty_csv_counts_missing_and_bom(client, session_id: str) -> None:
    """B3: BOM 不污染首列名；空值/NA 计入缺失；空行不计入行数。"""
    resp = _upload(client, session_id, "dirty.csv", _DIRTY_CSV)

    assert resp.status_code == 200
    profile = resp.json()["profile"]
    assert profile["row_count"] == 4
    assert set(profile["columns"]) == {"姓名", "年龄", "得分"}
    assert profile["columns"]["年龄"]["missing"] == 1
    assert profile["columns"]["得分"]["missing"] == 2


def test_two_uploads_create_independent_workspaces(client, session_id: str) -> None:
    """B4: 同会话多表 → dataset_id 唯一、互不覆盖、首表保持激活。"""
    first = _upload(client, session_id, "first.csv", CSV).json()
    second = _upload(
        client,
        session_id,
        "second.csv",
        "blood_pressure,weight\n120,60\n130,65\n".encode("utf-8"),
    ).json()

    assert first["dataset_id"] != second["dataset_id"]
    session = manager.get(session_id)
    assert session is not None
    assert set(session.datasets) == {first["dataset_id"], second["dataset_id"]}
    assert session.active_dataset_id == first["dataset_id"]
    assert session.datasets[first["dataset_id"]].profile.column_count == 2
    assert session.datasets[second["dataset_id"]].profile.column_count == 2


def test_header_only_csv_is_accepted_with_zero_rows(client, session_id: str) -> None:
    """B3: 只有表头的数据可解析，画像行数为 0（前端据此提示补充数据）。"""
    resp = _upload(client, session_id, "header.csv", b"age,city\n")

    assert resp.status_code == 200
    assert resp.json()["profile"]["row_count"] == 0
    assert resp.json()["profile"]["column_count"] == 2
