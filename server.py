from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse
import uvicorn
import threading
from fastmcp import FastMCP
import httpx
import os
import json
from typing import Optional, List

mcp = FastMCP("warframe-items")

WARFRAME_ITEMS_BASE_URL = "https://raw.githubusercontent.com/WFCD/warframe-items/master/data/json"

KNOWN_CATEGORIES = [
    "Arcanes", "Archwing", "Arch-Gun", "Arch-Melee", "Corpus", "Enemy",
    "Fish", "Gear", "Glyphs", "Melee", "Misc", "Mods", "Pets", "Primary",
    "Quests", "Relics", "Resources", "Secondary", "Sentinels", "SentinelWeapons",
    "Skins", "Warframes"
]

ENEMY_CATEGORIES = ["Enemy", "Corpus"]

_item_cache: dict = {}

async def fetch_category(category: str, client: httpx.AsyncClient) -> list:
    """Fetch items for a specific category from the WFCD GitHub raw JSON."""
    if category in _item_cache:
        return _item_cache[category]
    url = f"{WARFRAME_ITEMS_BASE_URL}/{category}.json"
    try:
        response = await client.get(url, timeout=30.0)
        if response.status_code == 200:
            data = response.json()
            _item_cache[category] = data
            return data
    except Exception:
        pass
    return []


async def fetch_all_items(categories: Optional[List[str]], ignore_enemies: bool, client: httpx.AsyncClient) -> list:
    """Fetch items from specified categories or all categories."""
    cats = categories if categories else KNOWN_CATEGORIES
    if ignore_enemies:
        cats = [c for c in cats if c not in ENEMY_CATEGORIES]
    all_items = []
    for cat in cats:
        items = await fetch_category(cat, client)
        all_items.extend(items)
    return all_items


@mcp.tool()
async def get_items(
    category: Optional[str] = None,
    ignoreEnemies: bool = True,
    i18n: Optional[str] = None,
    i18nOnObject: bool = False
) -> dict:
    """Retrieve all Warframe items or filter by category (e.g., 'Warframes', 'Primary', 'Secondary', 'Melee', 'Mods', 'Archwing'). Optionally supports i18n localization."""
    async with httpx.AsyncClient() as client:
        if category:
            matched_cat = None
            for known in KNOWN_CATEGORIES:
                if known.lower() == category.lower():
                    matched_cat = known
                    break
            if not matched_cat:
                return {"error": f"Unknown category '{category}'. Use get_item_categories to see valid options.", "items": []}
            if ignoreEnemies and matched_cat in ENEMY_CATEGORIES:
                return {"items": [], "count": 0, "category": category, "note": "Category excluded because ignoreEnemies=True"}
            items = await fetch_category(matched_cat, client)
        else:
            cats = KNOWN_CATEGORIES
            if ignoreEnemies:
                cats = [c for c in cats if c not in ENEMY_CATEGORIES]
            items = []
            for cat in cats:
                cat_items = await fetch_category(cat, client)
                items.extend(cat_items)

        result = {"items": items, "count": len(items)}
        if category:
            result["category"] = category
        if i18n:
            result["i18n_locale"] = i18n
            result["note"] = "i18n locale specified, but translation overlay is not available in this server mode. Items shown in English."
        return result


@mcp.tool()
async def find_item(uniqueName: str) -> dict:
    """Look up a single Warframe item by its unique internal name (uniqueName). Returns full details such as stats, components, drop locations, and polarities."""
    async with httpx.AsyncClient() as client:
        for cat in KNOWN_CATEGORIES:
            items = await fetch_category(cat, client)
            for item in items:
                if isinstance(item, dict) and item.get("uniqueName") == uniqueName:
                    return {"found": True, "item": item, "category": cat}
        return {"found": False, "uniqueName": uniqueName, "message": "Item not found. Ensure the uniqueName is exact (e.g., '/Lotus/Powersuits/Volt/Volt')."}


@mcp.tool()
async def resolve_mods(upgrades: List[dict]) -> dict:
    """Resolve a list of mod or arcane unique names (with optional ranks) into their full item data, separating results into mods and arcanes arrays."""
    async with httpx.AsyncClient() as client:
        mods_data = await fetch_category("Mods", client)
        arcanes_data = await fetch_category("Arcanes", client)

        all_mods_map = {item["uniqueName"]: item for item in mods_data if isinstance(item, dict) and "uniqueName" in item}
        all_arcanes_map = {item["uniqueName"]: item for item in arcanes_data if isinstance(item, dict) and "uniqueName" in item}

        resolved_mods = []
        resolved_arcanes = []
        not_found = []

        for upgrade in upgrades:
            uname = upgrade.get("uniqueName", "")
            rank = upgrade.get("rank", None)
            if uname in all_arcanes_map:
                entry = dict(all_arcanes_map[uname])
                if rank is not None:
                    entry["resolvedRank"] = rank
                resolved_arcanes.append(entry)
            elif uname in all_mods_map:
                entry = dict(all_mods_map[uname])
                if rank is not None:
                    entry["resolvedRank"] = rank
                resolved_mods.append(entry)
            else:
                not_found.append(uname)

        return {
            "mods": resolved_mods,
            "arcanes": resolved_arcanes,
            "notFound": not_found,
            "summary": {
                "modsResolved": len(resolved_mods),
                "arcanesResolved": len(resolved_arcanes),
                "notFound": len(not_found)
            }
        }


@mcp.tool()
async def parse_color(hex: str) -> dict:
    """Parse a hex color string and find matching Warframe color palette entries."""
    hex_clean = hex.lstrip("#").upper()
    if len(hex_clean) not in (3, 6, 8):
        return {"error": "Invalid hex color. Provide a 3, 6, or 8 character hex string.", "hex": hex}

    if len(hex_clean) == 3:
        hex_clean = "".join(c * 2 for c in hex_clean)

    is_transparent = len(hex_clean) == 8 and hex_clean[:2] == "00"

    r = int(hex_clean[0:2], 16) if len(hex_clean) >= 6 else 0
    g = int(hex_clean[2:4], 16) if len(hex_clean) >= 6 else 0
    b = int(hex_clean[4:6], 16) if len(hex_clean) >= 6 else 0

    async with httpx.AsyncClient() as client:
        try:
            palettes_url = "https://raw.githubusercontent.com/WFCD/warframe-items/master/data/json/Misc.json"
            # Color palette data isn't directly in the items JSON, so we return the parsed info
            pass
        except Exception:
            pass

    return {
        "hex": f"#{hex_clean}",
        "rgb": {"r": r, "g": g, "b": b},
        "isTransparent": is_transparent,
        "matches": [],
        "note": "Palette matching requires the full @wfcd/items Node.js library with embedded palette data. This server returns parsed color info only."
    }


@mcp.tool()
async def map_warframe_colors(colors: str) -> dict:
    """Convert a raw Warframe color configuration object (with slots t0, t1, t2, t3, m0, m1, en, en1) into a structured ColorMap with named slots."""
    try:
        raw = json.loads(colors)
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON: {str(e)}", "input": colors}

    def parse_hex(h):
        if not h:
            return None
        clean = h.lstrip("#").upper()
        if len(clean) == 3:
            clean = "".join(c * 2 for c in clean)
        if len(clean) not in (6, 8):
            return None
        is_transparent = len(clean) == 8 and clean[:2] == "00"
        r = int(clean[0:2], 16)
        g = int(clean[2:4], 16)
        b = int(clean[4:6], 16)
        return {"hex": f"#{clean}", "rgb": {"r": r, "g": g, "b": b}, "isTransparent": is_transparent}

    color_map = {
        "primary": parse_hex(raw.get("t0")),
        "secondary": parse_hex(raw.get("t1")),
        "tertiary": parse_hex(raw.get("t2")),
        "accents": parse_hex(raw.get("t3")),
        "emissive": [p for p in [parse_hex(raw.get("m0")), parse_hex(raw.get("m1"))] if p is not None],
        "energy": [p for p in [parse_hex(raw.get("en")), parse_hex(raw.get("en1"))] if p is not None]
    }

    return {
        "colorMap": color_map,
        "rawInput": raw,
        "slots": {
            "t0": "primary",
            "t1": "secondary",
            "t2": "tertiary",
            "t3": "accents",
            "m0": "emissive[0]",
            "m1": "emissive[1]",
            "en": "energy[0]",
            "en1": "energy[1]"
        }
    }


@mcp.tool()
async def search_items(
    query: str,
    category: Optional[str] = None,
    i18n: Optional[str] = None
) -> dict:
    """Search Warframe items by name, type, or other text-based fields within a given category. Returns matching items from the full dataset."""
    if not query or len(query.strip()) == 0:
        return {"error": "Query cannot be empty.", "results": []}

    query_lower = query.lower().strip()

    async with httpx.AsyncClient() as client:
        if category:
            matched_cat = None
            for known in KNOWN_CATEGORIES:
                if known.lower() == category.lower():
                    matched_cat = known
                    break
            if not matched_cat:
                return {"error": f"Unknown category '{category}'. Use get_item_categories to see valid options.", "results": []}
            all_items = await fetch_category(matched_cat, client)
            cats_searched = [matched_cat]
        else:
            all_items = []
            for cat in KNOWN_CATEGORIES:
                cat_items = await fetch_category(cat, client)
                for item in cat_items:
                    if isinstance(item, dict):
                        item["_sourceCategory"] = cat
                all_items.extend(cat_items)
            cats_searched = KNOWN_CATEGORIES

        results = []
        for item in all_items:
            if not isinstance(item, dict):
                continue
            name = item.get("name", "")
            item_type = item.get("type", "")
            description = item.get("description", "")
            unique_name = item.get("uniqueName", "")
            if (
                query_lower in name.lower()
                or query_lower in item_type.lower()
                or query_lower in description.lower()
                or query_lower in unique_name.lower()
            ):
                results.append(item)

    return {
        "query": query,
        "results": results,
        "count": len(results),
        "categoriesSearched": cats_searched
    }


@mcp.tool()
async def get_item_categories() -> dict:
    """List all available item categories in the Warframe items dataset."""
    return {
        "categories": KNOWN_CATEGORIES,
        "count": len(KNOWN_CATEGORIES),
        "enemyCategories": ENEMY_CATEGORIES,
        "note": "Enemy categories are excluded by default when using get_items or search_items with ignoreEnemies=True.",
        "usage": "Pass any of these category names to get_items(category=...) or search_items(category=...) to filter results."
    }




_SERVER_SLUG = "warframe-items"

def _track(tool_name: str, ua: str = ""):
    try:
        import urllib.request, json as _json
        data = _json.dumps({"slug": _SERVER_SLUG, "event": "tool_call", "tool": tool_name, "user_agent": ua}).encode()
        req = urllib.request.Request("https://www.volspan.dev/api/analytics/event", data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=1)
    except Exception:
        pass

async def health(request):
    return JSONResponse({"status": "ok", "server": mcp.name})

async def tools(request):
    registered = await mcp.list_tools()
    tool_list = [{"name": t.name, "description": t.description or ""} for t in registered]
    return JSONResponse({"tools": tool_list, "count": len(tool_list)})

mcp_app = mcp.http_app(transport="streamable-http")

class _FixAcceptHeader:
    """Ensure Accept header includes both types FastMCP requires."""
    def __init__(self, app):
        self.app = app
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            accept = headers.get(b"accept", b"").decode()
            if "text/event-stream" not in accept:
                new_headers = [(k, v) for k, v in scope["headers"] if k != b"accept"]
                new_headers.append((b"accept", b"application/json, text/event-stream"))
                scope = dict(scope, headers=new_headers)
        await self.app(scope, receive, send)

app = _FixAcceptHeader(Starlette(
    routes=[
        Route("/health", health),
        Route("/tools", tools),
        Mount("/", mcp_app),
    ],
    lifespan=mcp_app.lifespan,
))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
