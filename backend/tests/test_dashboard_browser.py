"""Desktop dashboard behavior against the built UI and isolated fake backend."""
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest

from backend.tests.test_browser import (  # noqa: F401
    FRONTEND_DIST, PHONE_PIN, browser, expect, page, send, server, unlock,
)

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(not (FRONTEND_DIST / 'index.html').is_file(), reason='build frontend first'),
]
ARTIFACTS = Path(__file__).resolve().parents[2] / 'scratch' / 'ui-redesign'


@pytest.mark.parametrize('width,height', [(1920, 1080), (1366, 768), (1024, 720)])
def test_dashboard_input_stays_visible_and_workspace_scrolls(page, server, width, height):
    page.set_viewport_size({'width': width, 'height': height})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    unlock(page, server, elevate=False)
    command = page.get_by_role('textbox', name='Command', exact=True)
    expect(command).to_be_visible()
    assert page.locator('header').get_by_role('textbox', name='Command').count() == 0
    box = command.bounding_box()
    assert height - 150 < box['y'] < height - 20
    assert box['y'] + box['height'] <= height - 10
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    main = page.locator('.dashboard-main')
    assert main.evaluate('(el) => el.scrollHeight <= el.clientHeight + 1')

    expect(page.locator('.workspace-browser')).to_have_count(0)
    expect(page.locator('.workspace-connections path')).to_have_count(0)
    eye = page.locator('.workspace-eye-art')
    initial_eye = eye.bounding_box()
    scene = page.locator('.workspace-scene').bounding_box()
    assert abs(initial_eye['x'] + initial_eye['width'] / 2 - scene['x'] - scene['width'] / 2) < 2
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ARTIFACTS / f'eye-home-{width}.png'))
    page.get_by_role('button', name='Projects', exact=True).click()
    projects = page.get_by_role('textbox', name='Filter Projects', exact=True)
    projects.fill('bims')
    rows = page.locator('.workspace-items button')
    expect(rows).to_have_count(1)
    expect(rows.first).to_contain_text('bims')
    rows.first.click()
    expect(page.get_by_role('region', name='Selected item')).to_be_visible()
    page.get_by_role('button', name='Close selection', exact=True).click()
    projects.fill('')
    page.get_by_role('button', name='Hide connections').click()
    expect(page.locator('.workspace-browser')).to_have_count(0)
    send(page, 'how many project i have')
    expect(page.get_by_role('list', name='Connected Projects')).to_be_visible()
    expect(page.locator('.workspace-items button')).to_have_count(3)
    expect(page.locator('.workspace-connections path')).not_to_have_count(0)
    assert abs(eye.bounding_box()['width'] - initial_eye['width']) < 1
    reply = page.get_by_role('region', name='Current response')
    expect(reply).to_be_visible()
    expect(page.get_by_text('Latest response', exact=True)).to_have_count(0)
    assert reply.evaluate('(el) => getComputedStyle(el).backgroundColor') == 'rgba(0, 0, 0, 0)'
    assert reply.evaluate('(el) => getComputedStyle(el).borderTopWidth') == '0px'
    assert page.get_by_role('button', name='History', exact=True).count() == 1
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ARTIFACTS / f'dashboard-{width}.png'))
    page.get_by_role('button', name='History', exact=True).first.click()
    dialog = page.get_by_role('dialog', name='Conversation history', exact=True)
    expect(dialog).to_be_visible()
    expect(dialog.get_by_role('log', name='Conversation', exact=True)).to_contain_text('bims')
    expect(dialog).to_contain_text('citizengraph')
    expect(dialog).to_contain_text('other')
    dialog.get_by_role('button', name='Close conversation history').press('Shift+Tab')
    assert page.evaluate("document.querySelector('dialog').contains(document.activeElement)")
    assert command.bounding_box()['y'] + command.bounding_box()['height'] <= height - 10
    page.get_by_role('button', name='Close conversation history').click()
    if width < 1200:
        page.get_by_role('button', name='Today', exact=True).click()
        expect(page.get_by_role('complementary', name='Today', exact=True)).to_be_visible()
        page.get_by_role('button', name='Close Today', exact=True).click()
        expect(page.get_by_role('button', name='Today', exact=True)).to_be_focused()
    assert not errors


def test_dashboard_typing_slash_commands_and_click_confirmation(page, server):
    page.add_init_script('''
      window.SpeechRecognition = class {
        constructor() { window.dashboardRecognition = this; }
        start() {}
        stop() { this.stopped = true; this.onend?.(); }
        abort() { this.aborted = true; }
      };
    ''')
    unlock(page, server, elevate=False)
    command = page.get_by_role('textbox', name='Command', exact=True)
    command.fill('hello')
    command.press('Space')
    command.press('Shift+Enter')
    expect(command).to_have_value('hello \n')
    command.fill('/vo')
    expect(page.get_by_role('listbox', name='Commands')).to_be_visible()
    command.press('Tab')
    expect(command).to_have_value('/voice')
    command.press('Enter')
    voice = page.get_by_role('dialog', name='Voice settings')
    expect(voice).to_be_visible()
    voice.get_by_role('button', name='Close', exact=True).click()
    command.fill('keep this draft')
    microphone = page.get_by_role('button', name='Hold microphone to talk', exact=True)
    microphone.dispatch_event('pointerdown', {'button': 0, 'pointerId': 1})
    expect(page.get_by_text('Listening… speak now', exact=True)).to_be_visible()
    microphone.dispatch_event('pointercancel', {'pointerId': 1})
    expect(page.get_by_text('Listening… speak now', exact=True)).to_be_hidden()
    expect(command).to_have_value('keep this draft')
    assert page.evaluate('window.dashboardRecognition.stopped')
    send(page, 'start the bims dev server')
    dialog = page.get_by_role('alertdialog')
    expect(dialog).to_contain_text('npm run dev')
    command.fill('yes')
    command.press('Enter')
    expect(dialog).to_be_visible()
    assert not server.ran
    dialog.get_by_role('button', name='Deny', exact=True).click()
    expect(dialog).to_be_hidden()
    assert not server.ran
    send(page, 'start the bims dev server')
    page.get_by_role('alertdialog').get_by_role('button', name='Run it').click()
    expect(page.get_by_role('region', name='Current response')).to_contain_text('Done: BIMS dev server')
    assert len(server.ran) == 1


def test_remote_session_remains_readonly(page, server):
    unlock(page, server, pin=PHONE_PIN, elevate=False)
    send(page, 'open notepad')
    expect(page.get_by_role('region', name='Current response')).to_contain_text('read only session')
    expect(page.get_by_role('button', name='Read-only', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Allowlisted Apps', exact=True)).to_have_count(0)
    expect(page.get_by_role('button', name='Settings', exact=True)).to_have_count(0)
    assert not server.ran


def test_dashboard_preserves_draft_while_working(page, server):
    pending = []
    page.route('**/api/chat', lambda route: pending.append(route))
    unlock(page, server, elevate=False)
    send(page, 'list my projects')
    expect(page.get_by_role('region', name='Current response')).to_have_count(0)
    expect(page.locator('.dashboard-state')).to_contain_text('Working')
    command = page.get_by_role('textbox', name='Command', exact=True)
    command.fill('my next request')
    expect(page.get_by_role('button', name='Send command', exact=True)).to_be_disabled()
    pending[0].continue_()
    expect(page.get_by_role('list', name='Connected Projects')).to_be_visible()
    expect(command).to_have_value('my next request')
    expect(page.get_by_role('button', name='Send command', exact=True)).to_be_enabled()


def test_dashboard_today_uses_real_data_and_long_lists_scroll(page, server):
    def status(route):
        response = route.fetch()
        if response.status != 200:
            route.fulfill(response=response)
            return
        data = response.json()
        data['project_cards'].extend({'name': f'Additional project with a long descriptive name {i}', 'has_handoff': False} for i in range(20))
        data['notes'] = [{'id': 7, 'text': 'Review the thesis presentation before the team meeting', 'ts': datetime.now(timezone.utc).isoformat()}]
        data['measurable_tasks'] = [{'id': 1, 'title': 'Research review', 'current_progress': 8, 'target_progress': 100}]
        data['calendar_events'] = [
            {'id': 1, 'title': 'Past meeting', 'start_date': '2020-01-01T08:00:00Z'},
            {'id': 2, 'title': 'Upcoming team meeting', 'start_date': (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()},
        ]
        data['weather_card'] = {'city': 'Calbayog', 'condition': 'Overcast', 'temp_c': 26, 'high_c': 27, 'low_c': 22, 'humidity': '80%', 'wind': '16 km/h', 'uv_index': '4', 'updated_at': '2:09 PM'}
        route.fulfill(response=response, json=data)

    page.route('**/api/status', status)
    unlock(page, server, elevate=False)
    today = page.get_by_role('complementary', name='Today', exact=True)
    expect(today).to_contain_text('Research review')
    expect(today).to_contain_text('8%')
    expect(today).not_to_contain_text('High')
    expect(today).not_to_contain_text('Medium')
    expect(today).to_contain_text('Upcoming team meeting')
    expect(today).not_to_contain_text('Past meeting')
    expect(today).to_contain_text('Calbayog')
    page.get_by_role('button', name='Projects', exact=True).click()
    listing = page.locator('.workspace-items')
    expect(listing.locator('button')).to_have_count(23)
    assert listing.evaluate('(el) => el.scrollHeight > el.clientHeight')
    before = page.get_by_label('Command', exact=True).bounding_box()
    listing.locator('button').last.scroll_into_view_if_needed()
    after = page.get_by_label('Command', exact=True).bounding_box()
    assert abs(before['y'] - after['y']) < 1
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ARTIFACTS / 'dashboard-populated.png'))


def test_dashboard_floating_text_follows_speech_and_history_stays_complete(page, server):
    page.emulate_media(reduced_motion='no-preference')
    page.set_viewport_size({'width': 1366, 'height': 768})
    page.add_init_script("""
      window.captionUtterances = [];
      window.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };
      Object.defineProperty(window, 'speechSynthesis', { value: {
        getVoices: () => [], addEventListener() {}, removeEventListener() {},
        cancel() {}, speak(utterance) { window.captionUtterances.push(utterance); }
      }});
    """)
    unlock(page, server, elevate=False)
    stage = page.get_by_role('region', name='Workspace')
    original_height = stage.bounding_box()['height']
    original_eye = page.locator('.workspace-eye-art').bounding_box()['width']
    send(page, 'list my projects')
    floating = page.get_by_role('region', name='Current response')
    expect(floating).to_contain_text('You have')
    assert abs(stage.bounding_box()['height'] - original_height) < 1
    assert abs(page.locator('.workspace-eye-art').bounding_box()['width'] - original_eye) < 1
    page.evaluate("window.captionUtterances[0].onstart(); window.captionUtterances[0].onboundary({charIndex: window.captionUtterances[0].text.indexOf('other')})")
    expect(floating).to_have_text('other.')
    expect(floating).not_to_contain_text('bims')
    page.get_by_role('button', name='History', exact=True).click()
    history = page.get_by_role('dialog', name='Conversation history')
    expect(history).to_contain_text('list my projects')
    expect(history).to_contain_text('bims')
    expect(history).to_contain_text('citizengraph')
    expect(history).to_contain_text('other')
    page.wait_for_function("getComputedStyle(document.querySelector('dialog')).opacity === '1' && getComputedStyle(document.querySelector('dialog [role=log]').lastElementChild).opacity === '1'")
    page.screenshot(path=str(ARTIFACTS / 'conversation-window.png'))
    page.keyboard.press('Escape')
    expect(history).to_have_count(0)
    expect(page.get_by_role('button', name='History', exact=True)).to_be_focused()
    page.get_by_role('button', name='Stop speaking', exact=True).click()
    expect(floating).to_have_text('other.')

    # One sentence/phrase replaces the previous one; captions never grow a transcript.
    page.route('**/api/chat', lambda route: route.fulfill(json={'reply': 'First sentence. Second sentence. Third sentence.', 'ok': True}))
    send(page, 'three sentences please')
    expect(page.locator('.workspace-browser')).to_have_count(0)
    expect(floating).to_have_text('First sentence.')
    page.evaluate("window.captionUtterances[1].onstart()")
    expect(floating).to_have_text('First sentence.')
    page.evaluate("window.captionUtterances[1].onend()")
    expect(page.get_by_role('button', name='Stop speaking', exact=True)).to_be_visible()
    page.evaluate("window.captionUtterances[2].onstart()")
    expect(floating).to_have_text('Second sentence.')
    expect(floating).not_to_contain_text('First')
    page.evaluate("window.captionUtterances[0].onend()")
    expect(floating).to_have_text('Second sentence.')
    page.evaluate("window.captionUtterances[2].onend(); window.captionUtterances[3].onstart()")
    expect(floating).to_have_text('Third sentence.')
    page.evaluate("window.captionUtterances[3].onend()")
    expect(floating).to_have_text('Third sentence.')
    assert abs(page.locator('.workspace-eye-art').bounding_box()['width'] - original_eye) < 1
    page.screenshot(path=str(ARTIFACTS / 'lyric-response-1366.png'))

    # Unavailable voices use a paced, single-line reading fallback.
    send(page, 'again please')
    expect(floating).to_have_text('First sentence.')
    page.evaluate("window.captionUtterances[4].onerror({error: 'synthesis-unavailable'})")
    expect(floating).to_have_text('Second sentence.', timeout=4000)
    expect(floating).to_have_text('Third sentence.', timeout=4000)

    # Reduced motion removes visual animation, while keeping one current caption.
    page.emulate_media(reduced_motion='reduce')
    send(page, 'once more please')
    expect(floating).to_have_text('First sentence.')
    assert floating.locator('p').evaluate('(el) => getComputedStyle(el).animationName') == 'none'

    # Repeating the same reply while muted must start its reading captions afresh.
    send(page, '/voice')
    voice = page.get_by_role('dialog', name='Voice settings')
    voice.get_by_role('button', name='Mute', exact=True).click()
    voice.get_by_role('button', name='Close', exact=True).click()
    send(page, 'muted repeat please')
    expect(floating).to_have_text('First sentence.')
    expect(floating).to_have_text('Second sentence.', timeout=4000)
    expect(page.get_by_role('button', name='Stop speaking', exact=True)).to_have_count(0)


def test_dashboard_connections_follow_context_and_manual_navigation(page, server):
    unlock(page, server, elevate=False)
    expect(page.locator('.workspace-browser')).to_have_count(0)
    send(page, 'list my projects')
    expect(page.get_by_role('list', name='Connected Projects')).to_be_visible()
    send(page, 'open notepad')
    expect(page.get_by_role('list', name='Connected Apps')).to_be_visible()
    expect(page.get_by_role('list', name='Connected Projects')).to_have_count(0)
    page.get_by_role('button', name='Hide connections').click()
    expect(page.locator('.workspace-browser')).to_have_count(0)
    page.get_by_role('button', name='Allowlisted Apps', exact=True).click()
    expect(page.get_by_role('list', name='Connected Apps')).to_be_visible()
    page.get_by_role('button', name='Home', exact=True).click()
    expect(page.locator('.workspace-browser')).to_have_count(0)
    send(page, 'hello nightmare')
    expect(page.get_by_role('region', name='Current response')).to_be_visible()
    expect(page.locator('.workspace-browser')).to_have_count(0)
