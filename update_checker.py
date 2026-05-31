"""
自動更新チェックモジュール
GitHub Releases APIを使って新バージョンを検知し、UIに通知する。

使い方 (main.py に追記):
    from update_checker import router as update_router
    app.include_router(update_router)
"""

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api", tags=["update"])

# ★ GitHubリポジトリを自分のものに変更
GITHUB_OWNER = "shoji-dot"
GITHUB_REPO = "CTM-"

# ★ このアプリの現在バージョン（リリース時に更新）
CURRENT_VERSION = "1.0.0"


def version_tuple(v: str):
    """バージョン文字列 '1.2.3' をタプル (1, 2, 3) に変換"""
    return tuple(int(x) for x in v.lstrip("v").split("."))


@router.get("/check-update")
async def check_update():
    """
    GitHub Releases から最新バージョンを取得して比較。
    レスポンス例:
        {"update_available": true, "latest_version": "1.1.0",
         "download_url": "https://github.com/.../releases/latest"}
    """
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers={"Accept": "application/vnd.github.v3+json"})
            resp.raise_for_status()
            data = resp.json()

        latest_version = data.get("tag_name", "").lstrip("v")
        release_url = data.get("html_url", f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest")

        # インストーラーのダウンロードURLを探す
        download_url = release_url
        for asset in data.get("assets", []):
            if asset["name"].endswith("_installer.exe"):
                download_url = asset["browser_download_url"]
                break

        update_available = version_tuple(latest_version) > version_tuple(CURRENT_VERSION)

        return JSONResponse({
            "update_available": update_available,
            "current_version": CURRENT_VERSION,
            "latest_version": latest_version,
            "download_url": download_url,
            "release_notes": data.get("body", "")[:500],  # リリースノート冒頭500文字
        })

    except httpx.TimeoutException:
        return JSONResponse({"update_available": False, "error": "timeout"}, status_code=200)
    except Exception as e:
        return JSONResponse({"update_available": False, "error": str(e)}, status_code=200)


@router.get("/version")
async def get_version():
    """現在のバージョンを返す"""
    return {"version": CURRENT_VERSION}
