import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any

# ルール遵守: パスは config.common を使用
from config.common import OUTPUT_RDE_DIR, get_dynamic_file_path

# ルール遵守: HTTP は net.http_helpers を使用（直接 requests 禁止）
from net.http_helpers import proxy_get

logger = logging.getLogger(__name__)


# キャッシュファイルの場所（パス管理は config.common に準拠）
_CACHE_DIR = OUTPUT_RDE_DIR  # output/rde
_LATEST_FILE = get_dynamic_file_path('output/rde/entries_latest.json')
_ALL_FILE = get_dynamic_file_path('output/rde/entries_all.json')

# キャッシュTTL: 最大1日
_CACHE_TTL = timedelta(days=1)
_UTC = timezone.utc


class EntrySummary:
	def __init__(self,
				 entry_id: str,
				 status: Optional[str],
				 start_time: Optional[str],
				 data_name: Optional[str],
				 dataset_name: Optional[str],
				 created_by_user_id: Optional[str],
				 created_by_name: Optional[str],
				 instrument_id: Optional[str],
				 instrument_name_ja: Optional[str],
				 instrument_name_en: Optional[str]):
		self.id = entry_id
		self.status = status
		self.startTime = start_time
		self.dataName = data_name
		self.datasetName = dataset_name
		self.createdByUserId = created_by_user_id
		self.createdByName = created_by_name
		self.instrumentId = instrument_id
		self.instrumentNameJa = instrument_name_ja
		self.instrumentNameEn = instrument_name_en

	def to_dict(self) -> Dict:
		return {
			"id": self.id,
			"status": self.status,
			"startTime": self.startTime,
			"dataName": self.dataName,
			"datasetName": self.datasetName,
			"createdByUserId": self.createdByUserId,
			"createdByName": self.createdByName,
			"instrumentId": self.instrumentId,
			"instrumentNameJa": self.instrumentNameJa,
			"instrumentNameEn": self.instrumentNameEn,
		}


def _now() -> datetime:
	return datetime.utcnow()


def _is_cache_valid(path: str) -> bool:
	try:
		import os
		if not os.path.exists(path):
			return False
		mtime = datetime.utcfromtimestamp(os.path.getmtime(path))
		return (_now() - mtime) <= _CACHE_TTL
	except Exception:
		return False


def _load_cache(path: str) -> List[Dict]:
	try:
		with open(path, 'r', encoding='utf-8') as f:
			return json.load(f)
	except Exception:
		return []


def _save_cache(path: str, entries: List[Dict]) -> None:
	try:
		import os
		os.makedirs(_CACHE_DIR, exist_ok=True)
		with open(path, 'w', encoding='utf-8') as f:
			json.dump(entries, f, ensure_ascii=False, indent=2)
	except Exception as e:
		logger.warning(f"キャッシュ保存に失敗: {path}: {e}")

def clear_cache() -> None:
	"""最新/全件キャッシュを削除"""
	import os
	try:
		removed = []
		for p in (_LATEST_FILE, _ALL_FILE):
			if os.path.exists(p):
				os.remove(p)
				removed.append(p)
		if removed:
			logger.info(f"[登録状況] キャッシュ削除: {removed}")
		else:
			logger.info("[登録状況] キャッシュファイルは存在しませんでした")
	except Exception as e:
		logger.warning(f"[登録状況] キャッシュ削除に失敗: {e}")

def has_valid_cache() -> bool:
	"""いずれかのキャッシュがTTL内で有効か判定"""
	return _is_cache_valid(_LATEST_FILE) or _is_cache_valid(_ALL_FILE)


def _collect_cache_metadata(cache_type: str, path: str) -> Optional[Dict[str, Any]]:
	"""キャッシュファイルのメタ情報を収集"""
	import os

	if not os.path.exists(path):
		return None
	try:
		updated_at = datetime.fromtimestamp(os.path.getmtime(path), tz=_UTC)
		size = os.path.getsize(path)
		entries = _load_cache(path)
		count = len(entries)
		return {
			"type": cache_type,
			"path": path,
			"updated_at": updated_at,
			"size": size,
			"count": count,
		}
	except Exception as exc:
		logger.debug("キャッシュメタ情報の収集に失敗: path=%s err=%s", path, exc)
		return None


def get_cache_metadata() -> List[Dict[str, Any]]:
	"""現在のキャッシュ状態を返す"""
	metadata: List[Dict[str, Any]] = []
	for cache_type, path in (("latest", _LATEST_FILE), ("all", _ALL_FILE)):
		info = _collect_cache_metadata(cache_type, path)
		if info:
			metadata.append(info)
	return metadata


def _build_entries_url(limit: int, offset: int) -> str:
	base = "https://rde-entry-api-arim.nims.go.jp/entries"
	params = (
		f"page%5Blimit%5D={limit}"
		f"&page%5Boffset%5D={offset}"
		f"&include=instrument%2CcreatedBy%2CrestructureRequest"
		f"&fields%5Bentry%5D=startTime%2CdataName%2CdatasetName%2Cstatus"
		f"&fields%5Buser%5D=createdBy%2CuserName"
		f"&fields%5Binstrument%5D=nameJa%2CnameEn"
	)
	return f"{base}?{params}"


def _parse_entries(resp_json: Dict) -> List[EntrySummary]:
	data = resp_json.get("data") or []
	included = resp_json.get("included") or []
	# id→included辞書化
	inc_by_id = {}
	for inc in included:
		t = inc.get("type")
		i = inc.get("id")
		if t and i:
			inc_by_id[(t, i)] = inc

	results: List[EntrySummary] = []
	for item in data:
		entry_id = item.get("id")
		attrs = item.get("attributes") or {}
		rel = item.get("relationships") or {}

		status = attrs.get("status")
		start_time = attrs.get("startTime")
		data_name = attrs.get("dataName")
		dataset_name = attrs.get("datasetName")

		created_by = rel.get("createdBy", {}).get("data") or {}
		created_user_id = created_by.get("id")
		created_user_name = None
		if created_user_id:
			u = inc_by_id.get(("user", created_user_id))
			if u:
				ua = u.get("attributes") or {}
				created_user_name = ua.get("userName")

		instr = rel.get("instrument", {}).get("data") or {}
		instrument_id = instr.get("id")
		instrument_name_ja = None
		instrument_name_en = None
		if instrument_id:
			ins = inc_by_id.get(("instrument", instrument_id))
			if ins:
				ia = ins.get("attributes") or {}
				instrument_name_ja = ia.get("nameJa")
				instrument_name_en = ia.get("nameEn")

		if entry_id:
			results.append(EntrySummary(
				entry_id,
				status,
				start_time,
				data_name,
				dataset_name,
				created_user_id,
				created_user_name,
				instrument_id,
				instrument_name_ja,
				instrument_name_en,
			))
	return results


def fetch_latest(limit: int = 100, use_cache: bool = True) -> List[Dict]:
	logger.debug(f"[登録状況] fetch_latest invoked: limit={limit}, use_cache={use_cache}")
	# キャッシュが有効なら最新キャッシュ使用
	if use_cache and _is_cache_valid(_LATEST_FILE):
		logger.debug("[登録状況] 最新キャッシュ有効 - 読み込み")
		latest = _load_cache(_LATEST_FILE)
		# 全件キャッシュがある場合はマージ
		if _is_cache_valid(_ALL_FILE):
			logger.debug("[登録状況] 全件キャッシュ有効 - 最新とマージ")
			all_entries = {e.get('id'): e for e in _load_cache(_ALL_FILE)}
			for e in latest:
				all_entries[e.get('id')] = e
			_save_cache(_ALL_FILE, list(all_entries.values()))
		return latest

	# API 取得
	url = _build_entries_url(limit=limit, offset=0)
	headers = {
		'Accept': 'application/vnd.api+json',
		'Cache-Control': 'no-cache',
		'Pragma': 'no-cache',
		'Origin': 'https://rde-entry-arim.nims.go.jp',
		'Referer': 'https://rde-entry-arim.nims.go.jp/',
		# Authorization は http_helpers 側でBearer自動付与
	}
	try:
		logger.debug(f"[登録状況] GET {url}")
		resp = proxy_get(url, headers=headers)
		if not resp or resp.status_code != 200:
			logger.warning(f"entries 最新取得に失敗: status={getattr(resp, 'status_code', None)}")
			return _load_cache(_LATEST_FILE) if use_cache else []
		items = [e.to_dict() for e in _parse_entries(resp.json())]
		_save_cache(_LATEST_FILE, items)
		# 全件キャッシュが有効ならマージ
		if _is_cache_valid(_ALL_FILE):
			all_entries = {e.get('id'): e for e in _load_cache(_ALL_FILE)}
			for e in items:
				all_entries[e.get('id')] = e
			_save_cache(_ALL_FILE, list(all_entries.values()))
		return items
	except Exception as e:
		logger.exception(f"entries 最新取得で例外: {e}")
		return _load_cache(_LATEST_FILE) if use_cache else []


def fetch_all(default_chunk: int = 5000, use_cache: bool = True) -> List[Dict]:
	logger.debug(f"[登録状況] fetch_all invoked: chunk={default_chunk}, use_cache={use_cache}")
	# キャッシュが有効なら全件キャッシュを返す
	if use_cache and _is_cache_valid(_ALL_FILE):
		logger.debug("[登録状況] 全件キャッシュ有効 - 読み込み")
		return _load_cache(_ALL_FILE)

	# 反復ページングで全件取得
	offset = 0
	chunk = default_chunk
	collected: Dict[str, Dict] = {}
	headers = {
		'Accept': 'application/vnd.api+json',
		'Cache-Control': 'no-cache',
		'Pragma': 'no-cache',
		'Origin': 'https://rde-entry-arim.nims.go.jp',
		'Referer': 'https://rde-entry-arim.nims.go.jp/',
	}
	try:
		while True:
			url = _build_entries_url(limit=chunk, offset=offset)
			logger.debug(f"[登録状況] GET {url}")
			resp = proxy_get(url, headers=headers)
			if not resp or resp.status_code != 200:
				logger.warning(f"entries 全件取得失敗: status={getattr(resp, 'status_code', None)} offset={offset}")
				break
			parsed = [e.to_dict() for e in _parse_entries(resp.json())]
			for e in parsed:
				collected[e.get('id')] = e
			if len(parsed) < chunk:
				break
			offset += chunk

		all_list = list(collected.values())
		_save_cache(_ALL_FILE, all_list)
		# 仕様: 全件を取った場合は最新も取得し直す
		latest = fetch_latest(limit=100, use_cache=False)
		_save_cache(_LATEST_FILE, latest)
		return all_list
	except Exception as e:
		logger.exception(f"entries 全件取得で例外: {e}")
		return _load_cache(_ALL_FILE) if use_cache else []


def count_by_status(entries: List[Dict]) -> Dict[str, int]:
	result: Dict[str, int] = {}
	for e in entries:
		s = e.get('status') or 'UNKNOWN'
		result[s] = result.get(s, 0) + 1
	return result


def count_by_dataset(entries: List[Dict]) -> Dict[str, int]:
	result: Dict[str, int] = {}
	for e in entries:
		d = e.get('datasetName') or 'UNKNOWN'
		result[d] = result.get(d, 0) + 1
	return result

