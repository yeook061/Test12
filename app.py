import json
import os
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="쇼핑리스트", page_icon="🛒", layout="centered")

DATA_FILE = Path(__file__).parent / "items.json"
MAX_NAME = 50  # 이름 최대 글자 수
MAX_QTY = 99  # 수량 최대값

# 모든 CSS는 여기 한 곳에서 관리한다. (포인트 컬러는 .streamlit/config.toml의 primaryColor)
CUSTOM_CSS = """
<style>
/* 좁은 화면에서도 한 줄 배치를 유지 (입력행, 항목행) */
div[data-testid="stHorizontalBlock"] {
    flex-wrap: nowrap;
    align-items: center;
    gap: 0.5rem;
}
div[data-testid="stColumn"] { min-width: 0; }
/* 아이콘 버튼은 작고 가볍게 */
div[data-testid="stColumn"] button { padding: 0.25rem 0.6rem; }
/* 긴 이름은 잘라내지 않고 줄바꿈 */
div[data-testid="stColumn"] [data-testid="stMarkdownContainer"] p {
    white-space: normal;
    overflow-wrap: anywhere;
    margin: 0;
}
/* 입력창 안의 "Press Enter to submit form" 안내가 placeholder와 겹치지 않게 숨김 */
div[data-testid="InputInstructions"] { display: none; }
/* 푸터 숨김 */
footer { visibility: hidden; }
.empty-state { text-align: center; padding: 2.5rem 0; opacity: 0.7; }
.subtitle { margin-top: -0.8rem; opacity: 0.7; }
</style>
"""


# ---------- 데이터 저장/불러오기 ----------
@st.cache_resource
def get_lock():
    """같은 서버 안의 여러 세션이 동시에 파일을 고치지 않도록 하는 잠금"""
    return threading.Lock()


def load_items():
    """items.json에서 아이템을 불러온다. 파일이 없거나 깨져 있으면 빈 리스트."""
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    items = []
    for d in data:
        # 형식이 맞지 않는 항목은 건너뛴다
        if not isinstance(d, dict) or not str(d.get("name", "")).strip():
            continue
        try:
            quantity = max(1, int(d.get("quantity", 1)))
        except (TypeError, ValueError):
            quantity = 1
        items.append(
            {
                "id": str(d.get("id") or uuid.uuid4()),
                "name": str(d["name"]).strip(),
                "quantity": quantity,
                "checked": bool(d.get("checked", False)),
                "created_at": str(d.get("created_at", "")),
            }
        )
    return items


def save_items(items):
    """임시 파일에 쓴 뒤 교체해서 저장 중 파일이 깨지지 않게 한다."""
    try:
        tmp = DATA_FILE.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp, DATA_FILE)
    except OSError:
        st.session_state["save_failed"] = True


def update_items(change):
    """파일의 최신 목록을 읽어 변경을 적용하고 저장한다.
    (다른 세션이 먼저 바꾼 내용을 덮어쓰지 않기 위해 항상 파일 기준으로 처리)"""
    with get_lock():
        items = load_items()
        change(items)
        save_items(items)
    st.session_state["items"] = items


def init_state():
    # 매 실행마다 파일의 최신 내용으로 갱신해서 다른 세션의 변경을 반영
    with get_lock():
        st.session_state["items"] = load_items()
    st.session_state.setdefault("editing_id", None)
    st.session_state.setdefault("edit_error", False)
    st.session_state.setdefault("new_name", "")
    st.session_state.setdefault("new_qty", 1)
    ids = {i["id"] for i in st.session_state["items"]}
    if st.session_state["editing_id"] not in ids:
        st.session_state["editing_id"] = None  # 다른 세션이 지운 항목


def md_escape(text):
    """마크다운 문법 문자를 모두 이스케이프해서 입력한 그대로 보이게 한다.
    (ASCII 기호는 전부 이스케이프 가능: 링크 자동변환, :gray[] 같은 문법도 막힘)"""
    return re.sub(r"([!-/:-@\[-`{-~])", r"\\\1", text)


def plain_label(name, quantity):
    """화면에 보이지 않는 체크박스 접근성 라벨용 일반 텍스트.
    (라벨도 마크다운으로 해석되므로 기호는 공백으로 바꿔 링크 등이 생기지 않게 한다)"""
    text = re.sub(r"[!-/:-@\[-`{-~]", " ", name)
    text = " ".join(text.split()) or "항목"
    return f"{text} {quantity}개"


# ---------- 동작(콜백) ----------
def add_from_form():
    name = st.session_state["new_name"].strip()
    qty = st.session_state["new_qty"]
    if not name:
        st.session_state["add_error"] = "아이템 이름을 입력해주세요."
        return
    if qty is None or not (1 <= qty <= MAX_QTY):
        st.session_state["add_error"] = f"수량은 1~{MAX_QTY} 사이로 입력해주세요."
        return
    new_item = {
        "id": str(uuid.uuid4()),
        "name": name,
        "quantity": int(qty),
        "checked": False,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    update_items(lambda items: items.append(new_item))
    # 성공했을 때만 입력창 비우기 (오류 시에는 입력 내용 유지)
    st.session_state["new_name"] = ""
    st.session_state["new_qty"] = 1


def toggle_item(item_id):
    checked = st.session_state[f"chk_{item_id}"]

    def change(items):
        for item in items:
            if item["id"] == item_id:
                item["checked"] = checked

    update_items(change)


def delete_item(item_id):
    update_items(lambda items: items.__setitem__(
        slice(None), [i for i in items if i["id"] != item_id]
    ))
    if st.session_state["editing_id"] == item_id:
        st.session_state["editing_id"] = None


def clear_checked():
    update_items(lambda items: items.__setitem__(
        slice(None), [i for i in items if not i["checked"]]
    ))


def start_edit(item_id):
    st.session_state["editing_id"] = item_id  # 한 번에 하나만 수정
    st.session_state["edit_error"] = False


def cancel_edit():
    st.session_state["editing_id"] = None
    st.session_state["edit_error"] = False


def save_edit(item_id):
    name = st.session_state[f"edit_name_{item_id}"].strip()
    if not name:
        st.session_state["edit_error"] = True
        return
    qty = int(st.session_state[f"edit_qty_{item_id}"])

    def change(items):
        for item in items:
            if item["id"] == item_id:
                item["name"] = name
                item["quantity"] = qty

    update_items(change)
    st.session_state["editing_id"] = None
    st.session_state["edit_error"] = False


# ---------- 화면 ----------
def render_add_form():
    with st.form("add_form", clear_on_submit=False, border=False):
        col_name, col_qty, col_btn = st.columns([5, 2, 2], vertical_alignment="bottom")
        col_name.text_input(
            "아이템 이름",
            key="new_name",
            max_chars=MAX_NAME,
            placeholder="무엇을 살까요? (예: 우유)",
            label_visibility="collapsed",
        )
        col_qty.number_input(
            "수량",
            key="new_qty",
            step=1,
            label_visibility="collapsed",
            help=f"수량 (1~{MAX_QTY})",
        )
        col_btn.form_submit_button(
            "추가", type="primary", use_container_width=True, on_click=add_from_form
        )
    error = st.session_state.pop("add_error", None)  # 한 번만 표시
    if error:
        st.warning(error)


def render_progress():
    items = st.session_state["items"]
    total = len(items)
    done = sum(1 for i in items if i["checked"])
    st.progress(done / total if total else 0.0, text=f"완료 {done} / {total}")
    if total and done == total:
        st.success("모두 담았어요! 🎉")


def render_item(item):
    item_id = item["id"]
    if st.session_state["editing_id"] == item_id:
        col_name, col_qty = st.columns([3, 1])
        col_name.text_input(
            "이름 수정", value=item["name"], key=f"edit_name_{item_id}", max_chars=MAX_NAME
        )
        col_qty.number_input(
            "수량 수정",
            min_value=1,
            max_value=MAX_QTY,
            value=min(item["quantity"], MAX_QTY),
            step=1,
            key=f"edit_qty_{item_id}",
        )
        if st.session_state["edit_error"]:
            st.warning("이름을 입력해주세요.")
        col_save, col_cancel, _ = st.columns([1, 1, 3])
        col_save.button(
            "저장", key=f"save_{item_id}", on_click=save_edit, args=(item_id,), type="primary"
        )
        col_cancel.button("취소", key=f"cancel_{item_id}", on_click=cancel_edit)
        return

    # 다른 세션이 바꾼 체크 상태가 위젯에 반영되도록 렌더 전에 맞춘다
    st.session_state[f"chk_{item_id}"] = item["checked"]
    text = f"{md_escape(item['name'])} x{item['quantity']}"
    if item["checked"]:
        text = f":gray[~~{text}~~]"
    editing_other = st.session_state["editing_id"] is not None
    col_chk, col_text, col_edit, col_del = st.columns(
        [1, 6, 1.4, 1.4], vertical_alignment="center"
    )
    # 접근성용 이름은 일반 텍스트로 두고, 화면에 보이는 글자는 따로 표시
    col_chk.checkbox(
        plain_label(item["name"], item["quantity"]),
        key=f"chk_{item_id}",
        label_visibility="collapsed",
        on_change=toggle_item,
        args=(item_id,),
    )
    col_text.markdown(text)
    col_edit.button(
        "✏️",
        key=f"edit_{item_id}",
        on_click=start_edit,
        args=(item_id,),
        help="다른 항목을 수정하는 중에는 사용할 수 없어요" if editing_other else "수정",
        disabled=editing_other,  # 수정 중 다른 항목을 열어 입력 내용이 사라지는 것을 방지
    )
    col_del.button("🗑", key=f"del_{item_id}", on_click=delete_item, args=(item_id,), help="삭제")


def render_list():
    items = st.session_state["items"]
    if not items:
        st.markdown(
            '<div class="empty-state">🧺<br>아직 추가된 항목이 없어요</div>',
            unsafe_allow_html=True,
        )
        return
    render_progress()
    # 표시만 정렬: 미체크가 위, 체크된 항목이 아래 (저장 순서는 그대로)
    for item in sorted(items, key=lambda i: i["checked"]):
        with st.container(border=True):
            render_item(item)
    st.button(
        "체크된 항목 삭제",
        on_click=clear_checked,
        disabled=not any(i["checked"] for i in items),
    )


def main():
    init_state()
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.title("🛒 쇼핑리스트")
    st.markdown('<p class="subtitle">오늘 살 것을 적어보세요</p>', unsafe_allow_html=True)
    if st.session_state.pop("save_failed", False):
        st.warning("목록을 파일에 저장하지 못했어요. 새로고침하면 사라질 수 있어요.")
    render_add_form()
    st.divider()
    render_list()


main()
