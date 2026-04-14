import hashlib
import json
import re
import types

from horoscope_engine.cli import main


def _snapshot_fingerprint(text: str) -> str:
    normalized = text.replace("\r\n", "\n")
    normalized = re.sub(r"opastro\\s+\\d+\\.\\d+\\.\\d+", "opastro <VERSION>", normalized)
    normalized = re.sub(r"•\\s+\\d+\\.\\d+\\.\\d+", "• <VERSION>", normalized)
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n")).strip() + "\n"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def test_welcome_screen_is_default_when_no_args(capsys):
    code = main([])
    out = capsys.readouterr().out
    assert code == 0
    assert "OPASTRO" in out
    assert "Want deeper insights?" in out
    assert "Unlock full readings: https://numerologyapi.com" in out


def test_catalog_command_lists_core_entities(capsys):
    code = main(["catalog"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Periods" in out
    assert "Sections" in out
    assert "Signs" in out
    assert "Planets" in out


def test_horoscope_json_output_mode(capsys):
    code = main(["horoscope", "--period", "daily", "--sign", "ARIES", "--target-date", "2026-04-03", "--json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert code == 0
    assert payload["report_type"] == "horoscope"
    assert payload["period"] == "daily"
    assert payload["sign"] == "ARIES"


def test_birth_extras_require_birth_date(capsys):
    code = main(["horoscope", "--period", "daily", "--sign", "ARIES", "--birth-time", "09:30"])
    err = capsys.readouterr().err
    assert code == 2
    assert "Provide --birth-date" in err


def test_markdown_format_output(capsys):
    code = main(
        [
            "horoscope",
            "--period",
            "daily",
            "--sign",
            "ARIES",
            "--target-date",
            "2026-04-03",
            "--format",
            "markdown",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "# OPASTRO REPORT" in out
    assert "## General" in out


def test_html_export_output(tmp_path, capsys):
    export_path = tmp_path / "report.html"
    code = main(
        [
            "horoscope",
            "--period",
            "daily",
            "--sign",
            "ARIES",
            "--target-date",
            "2026-04-03",
            "--format",
            "html",
            "--export",
            str(export_path),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "<!doctype html>" in captured.out.lower()
    assert "saved output to" in captured.err
    assert export_path.exists()
    assert export_path.read_text().lower().startswith("<!doctype html>")


def test_profile_save_list_and_apply_defaults(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPASTRO_CONFIG_DIR", str(tmp_path / "cfg"))

    code = main(["profile", "save", "--name", "alpha", "--sign", "ARIES", "--format", "markdown", "--set-active"])
    assert code == 0

    code = main(["profile", "list"])
    out = capsys.readouterr().out
    assert code == 0
    assert "* alpha" in out

    code = main(["horoscope", "--period", "daily", "--target-date", "2026-04-03", "--format", "json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert code == 0
    assert payload["sign"] == "ARIES"


def test_init_interactive_creates_profile(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPASTRO_CONFIG_DIR", str(tmp_path / "cfg"))
    answers = iter(
        [
            "Dakidarts",  # user_name
            "ARIES",  # sign
            "n",  # save birth details
            "general,career",  # sections
            "markdown",  # format
            "sidereal",  # zodiac system
            "lahiri",  # ayanamsa
            "placidus",  # house system
            "true",  # node type
            "public",  # tenant id
            "day",  # wheel theme
            "#3ddd77",  # accent
            "OPASTRO",  # brand title
            "https://opastro.com",  # brand url
            "https://numerologyapi.com",  # premium url
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    code = main(["init", "--profile", "starter"])
    assert code == 0
    capsys.readouterr()

    code = main(["profile", "show", "--name", "starter"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert code == 0
    assert payload["name"] == "starter"
    assert payload["profile"]["user_name"] == "Dakidarts"
    assert payload["profile"]["sign"] == "ARIES"
    assert payload["profile"]["output_format"] == "markdown"
    assert payload["profile"]["sections"] == ["general", "career"]
    assert payload["profile"]["wheel_theme"] == "day"
    assert payload["profile"]["accent"] == "#3ddd77"


def test_command_alias_works_for_horoscope(capsys):
    code = main(["h", "--period", "daily", "--sign", "ARIES", "--target-date", "2026-04-03", "--json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert code == 0
    assert payload["report_type"] == "horoscope"


def test_typo_suggestion_for_unknown_command(capsys):
    code = main(["horoscpoe"])
    err = capsys.readouterr().err
    assert code == 2
    assert "Did you mean" in err
    assert "horoscope" in err


def test_completion_bash_output(capsys):
    code = main(["completion", "--shell", "bash"])
    out = capsys.readouterr().out
    assert code == 0
    assert "complete -F _opastro_complete opastro" in out
    assert "horoscope" in out
    assert "batch" in out


def test_explain_json_output_contains_factor_provenance(capsys):
    code = main(
        [
            "explain",
            "--kind",
            "horoscope",
            "--period",
            "daily",
            "--sign",
            "ARIES",
            "--target-date",
            "2026-04-03",
            "--json",
        ]
    )
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert code == 0
    assert payload["sections"]
    first = payload["sections"][0]
    assert "summary" in first
    assert "factors" in first
    assert first["factors"]
    assert "factor_type" in first["factors"][0]


def test_ui_no_interactive_fallback(capsys):
    code = main(
        [
            "ui",
            "--period",
            "daily",
            "--sign",
            "ARIES",
            "--target-date",
            "2026-04-03",
            "--no-interactive",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "UI fallback mode" in out
    assert "OPASTRO REPORT" in out


def test_doctor_fix_dry_run(capsys):
    code = main(["doctor", "--fix", "--dry-run"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Fix plan" in out
    assert "pip install -e .[dev]" in out
    assert "Post-fix check" not in out


def test_doctor_json_output(capsys):
    code = main(["doctor", "--json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert code == 0
    assert "python_executable" in payload
    assert "runtime_ok" in payload
    assert "dependencies" in payload
    assert payload["fix"]["requested"] is False


def test_doctor_fix_blocked_outside_virtualenv(monkeypatch, capsys):
    monkeypatch.setattr("horoscope_engine.cli.sys.prefix", "/usr")
    monkeypatch.setattr("horoscope_engine.cli.sys.base_prefix", "/usr")

    called = {"value": False}

    def _fake_run(*_args, **_kwargs):
        called["value"] = True
        return types.SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr("horoscope_engine.cli.subprocess.run", _fake_run)

    code = main(["doctor", "--fix"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Fix blocked" in out
    assert called["value"] is False


def test_analytics_disabled_by_default(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPASTRO_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("OPASTRO_ANALYTICS", raising=False)
    code = main(["catalog"])
    assert code == 0
    capsys.readouterr()
    assert not (tmp_path / "cfg" / "analytics-events.log").exists()


def test_analytics_opt_in_tracks_anonymized_events(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPASTRO_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("OPASTRO_ANALYTICS", "1")

    code = main(["catalog"])
    assert code == 0
    capsys.readouterr()

    code = main(["horoscpoe"])
    assert code == 2
    capsys.readouterr()

    analytics_path = tmp_path / "cfg" / "analytics-events.log"
    lines = [json.loads(line) for line in analytics_path.read_text().splitlines() if line.strip()]
    assert len(lines) >= 2
    success = lines[-2]
    failure = lines[-1]
    assert success["command"] == "catalog"
    assert success["status"] == "ok"
    assert success["exit_code"] == 0
    assert failure["command"] == "horoscpoe"
    assert failure["status"] == "error"
    assert failure["failure_category"] == "unknown_command"
    assert "cwd" not in success and "argv" not in success
    assert "cwd" not in failure and "argv" not in failure


def test_logger_path_uses_opastro_config_dir(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPASTRO_CONFIG_DIR", str(tmp_path / "cfg"))
    code = main(["logger", "path"])
    out = capsys.readouterr().out.strip()
    assert code == 0
    assert out.endswith("runtime-errors.log")
    assert str(tmp_path / "cfg") in out


def test_logger_captures_runtime_error_with_suggested_fixes(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPASTRO_CONFIG_DIR", str(tmp_path / "cfg"))

    code = main(["horoscope", "--period", "daily", "--birth-time", "09:30"])
    err = capsys.readouterr().err
    assert code == 2
    assert "Provide --birth-date" in err
    assert "inspect logs: opastro logger show" in err

    code = main(["logger", "show", "--limit", "1", "--json"])
    out = capsys.readouterr().out
    entries = json.loads(out)
    assert code == 0
    assert len(entries) == 1
    latest = entries[0]
    assert latest["error_type"] == "ValueError"
    assert "Provide --birth-date" in latest["error_message"]
    assert latest["command"][0] == "horoscope"
    assert latest["suggested_fixes"]
    assert any("birth-date" in item.lower() for item in latest["suggested_fixes"])


def test_logger_clear_removes_log_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPASTRO_CONFIG_DIR", str(tmp_path / "cfg"))
    main(["horoscope", "--period", "daily", "--birth-time", "09:30"])
    capsys.readouterr()

    code = main(["logger", "clear"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Cleared runtime error log" in out

    code = main(["logger", "show"])
    out = capsys.readouterr().out
    assert code == 0
    assert "No runtime errors logged yet" in out


def test_logger_shorthand_flags_route_to_show(capsys):
    code = main(["logger", "--limit", "1"])
    out = capsys.readouterr().out
    assert code == 0
    assert "OPASTRO LOGGER" in out


def test_batch_export_generates_multiple_files(tmp_path, capsys):
    export_dir = tmp_path / "batch"
    code = main(
        [
            "batch",
            "--kind",
            "horoscope",
            "--period",
            "daily",
            "--signs",
            "ARIES,TAURUS",
            "--date-from",
            "2026-04-03",
            "--date-to",
            "2026-04-04",
            "--format",
            "markdown",
            "--export-dir",
            str(export_dir),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "batch summary" in captured.err
    files = sorted(path.name for path in export_dir.glob("*.md"))
    assert len(files) == 4
    assert any("ARIES" in name for name in files)
    assert any("TAURUS" in name for name in files)


def test_root_help_uses_themed_tables(capsys):
    code = main(["--help"])
    out = capsys.readouterr().out
    assert code == 0
    assert "OPASTRO HELP" in out
    assert "Commands" in out
    assert "init (onboard)" in out
    assert "┌" in out or "+" in out


def test_command_help_uses_themed_tables(capsys):
    code = main(["doctor", "--help"])
    out = capsys.readouterr().out
    assert code == 0
    assert "opastro doctor" in out
    assert "Usage" in out


def test_golden_snapshot_welcome_output(monkeypatch, capsys):
    monkeypatch.setenv("OPASTRO_COLOR", "never")
    monkeypatch.setattr("horoscope_engine.cli._term_width", lambda: 96)
    code = main([])
    out = capsys.readouterr().out
    assert code == 0
    assert _snapshot_fingerprint(out) == "df3bcb929962bc19266dfbd20f30fb16fc8360a3fad58ed9dc8247f7312fd530"


def test_golden_snapshot_root_help_output(monkeypatch, capsys):
    monkeypatch.setenv("OPASTRO_COLOR", "never")
    monkeypatch.setattr("horoscope_engine.cli._term_width", lambda: 96)
    code = main(["--help"])
    out = capsys.readouterr().out
    assert code == 0
    assert _snapshot_fingerprint(out) == "07d426fc577804aeee198de5c49140ac35d62a7fa78ab8e3bb62523bc14c6442"


def test_golden_snapshot_logger_help_output(monkeypatch, capsys):
    monkeypatch.setenv("OPASTRO_COLOR", "never")
    monkeypatch.setattr("horoscope_engine.cli._term_width", lambda: 96)
    code = main(["logger", "--help"])
    out = capsys.readouterr().out
    assert code == 0
    assert _snapshot_fingerprint(out) == "612f76faed9e600f63a56cff4eb6cccf3d7fd0535a2f97a91ad799b994214b83"


def test_version_flag_prints_installed_version(capsys):
    code = main(["--version"])
    out = capsys.readouterr().out.strip()
    assert code == 0
    assert out.startswith("opastro ")


def test_init_template_natal_prefills_defaults(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPASTRO_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setattr("horoscope_engine.cli._detect_local_timezone", lambda: "Africa/Douala")
    answers = iter(
        [
            "",  # user_name
            "",  # sign
            "n",  # save birth details
            "",  # sections
            "",  # output format (template default)
            "",  # zodiac system
            "",  # ayanamsa
            "",  # house system
            "",  # node type
            "",  # tenant id
            "",  # wheel theme
            "",  # accent
            "",  # brand title
            "",  # brand url
            "",  # premium url
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    code = main(["init", "--profile", "natal-template", "--template", "natal"])
    assert code == 0
    capsys.readouterr()

    code = main(["profile", "show", "--name", "natal-template"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert code == 0
    profile = payload["profile"]
    assert profile["wheel_theme"] == "day"
    assert profile["accent"] == "#3ddd77"
    assert profile["brand_title"] == "OPASTRO"
    assert profile["brand_url"] == "https://opastro.com"
    assert profile["premium_url"] == "https://numerologyapi.com"
    assert profile["output_format"] == "markdown"
    assert profile["zodiac_system"] == "tropical"


def test_natal_command_exports_svg_png_map_pdf(tmp_path, capsys):
    wheel_svg = tmp_path / "wheel.svg"
    wheel_png = tmp_path / "wheel.png"
    house_map = tmp_path / "house-map.json"
    report_pdf = tmp_path / "natal.pdf"

    code = main(
        [
            "natal",
            "--birth-date",
            "2004-06-14",
            "--birth-time",
            "09:30",
            "--lat",
            "4.0511",
            "--lon",
            "9.7679",
            "--timezone",
            "Africa/Douala",
            "--wheel-theme",
            "day",
            "--wheel-svg",
            str(wheel_svg),
            "--wheel-png",
            str(wheel_png),
            "--house-map",
            str(house_map),
            "--pdf",
            str(report_pdf),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "OPASTRO NATAL REPORT" in captured.out
    assert wheel_svg.exists()
    assert wheel_png.exists()
    assert house_map.exists()
    assert report_pdf.exists()
    assert wheel_svg.read_text().lstrip().startswith("<svg")
    assert wheel_png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert report_pdf.read_bytes().startswith(b"%PDF")


def test_natal_split_exports_main_and_legends(tmp_path, capsys):
    split_dir = tmp_path / "split"
    code = main(
        [
            "natal",
            "--birth-date",
            "2004-06-14",
            "--birth-time",
            "09:30",
            "--lat",
            "4.0511",
            "--lon",
            "9.7679",
            "--timezone",
            "Africa/Douala",
            "--split",
            "--split-dir",
            str(split_dir),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "saved output to" in captured.err
    full_svg = split_dir / "natal-wheel.full.svg"
    main_svg = split_dir / "natal-wheel.main.svg"
    legends_svg = split_dir / "natal-wheel.legends.svg"
    combined_svg = split_dir / "natal-wheel.combined.svg"
    assert full_svg.exists()
    assert main_svg.exists()
    assert legends_svg.exists()
    assert combined_svg.exists()
    assert 'id="main-wheel"' in main_svg.read_text()
    assert 'id="legends"' in legends_svg.read_text()


def test_natal_split_png_exports(tmp_path, capsys):
    split_dir = tmp_path / "split-png"
    code = main(
        [
            "natal",
            "--birth-date",
            "2004-06-14",
            "--birth-time",
            "09:30",
            "--lat",
            "4.0511",
            "--lon",
            "9.7679",
            "--timezone",
            "Africa/Douala",
            "--split-png",
            "--split-dir",
            str(split_dir),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "saved output to" in captured.err
    assert (split_dir / "natal-wheel.main.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert (split_dir / "natal-wheel.legends.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert (split_dir / "natal-wheel.combined.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_natal_wheel_svg_split_api_response_shape():
    from fastapi.testclient import TestClient

    from horoscope_engine.main import app

    client = TestClient(app)
    payload = {
        "birth": {
            "date": "2004-06-14",
            "time": "09:30",
            "coordinates": {"latitude": 4.0511, "longitude": 9.7679},
            "timezone": "Africa/Douala",
        }
    }
    response = client.post(
        "/natal-birthchart/wheel.svg?theme=day&split=true&split_layout=side-by-side",
        json=payload,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["theme"] == "day"
    assert data["split_layout"] == "side-by-side"
    assert data["full_svg"].lstrip().startswith("<svg")
    assert data["main_wheel_svg"].lstrip().startswith("<svg")
    assert data["legends_svg"].lstrip().startswith("<svg")
    assert data["combined_svg"].lstrip().startswith("<svg")
    assert 'id="main-wheel"' in data["main_wheel_svg"]
    assert 'id="legends"' in data["legends_svg"]
    assert data["combined_width"] >= data["main_width"] + data["legends_width"]


def test_natal_wheel_svg_split_layout_stacked_changes_dimensions():
    from fastapi.testclient import TestClient

    from horoscope_engine.main import app

    client = TestClient(app)
    payload = {
        "birth": {
            "date": "2004-06-14",
            "time": "09:30",
            "coordinates": {"latitude": 4.0511, "longitude": 9.7679},
            "timezone": "Africa/Douala",
        }
    }
    side = client.post(
        "/natal-birthchart/wheel.svg?theme=day&split=true&split_layout=side-by-side",
        json=payload,
    ).json()
    stacked = client.post(
        "/natal-birthchart/wheel.svg?theme=day&split=true&split_layout=stacked",
        json=payload,
    ).json()
    assert side["split_layout"] == "side-by-side"
    assert stacked["split_layout"] == "stacked"
    assert stacked["combined_height"] > side["combined_height"]
    assert stacked["combined_width"] <= side["combined_width"]


def test_natal_wheel_parts_zip_endpoint_contains_expected_files():
    from io import BytesIO
    import zipfile

    from fastapi.testclient import TestClient

    from horoscope_engine.main import app

    client = TestClient(app)
    payload = {
        "birth": {
            "date": "2004-06-14",
            "time": "09:30",
            "coordinates": {"latitude": 4.0511, "longitude": 9.7679},
            "timezone": "Africa/Douala",
        }
    }
    response = client.post("/natal-birthchart/wheel.parts.zip?theme=night&split_layout=stacked", json=payload)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    archive = zipfile.ZipFile(BytesIO(response.content))
    names = set(archive.namelist())
    assert "natal-wheel.full.svg" in names
    assert "natal-wheel.main.svg" in names
    assert "natal-wheel.legends.svg" in names
    assert "natal-wheel.combined.svg" in names
    assert "natal-wheel.main.png" in names
    assert "natal-wheel.legends.png" in names
    assert "natal-wheel.combined.png" in names
    manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    assert manifest["split_layout"] == "stacked"


def test_profile_natal_defaults_apply_to_natal_exports(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPASTRO_CONFIG_DIR", str(tmp_path / "cfg"))
    wheel_svg = tmp_path / "wheel-profile.svg"

    code = main(
        [
            "profile",
            "save",
            "--name",
            "natal",
            "--set-active",
            "--user-name",
            "Dakidarts",
            "--wheel-theme",
            "day",
            "--accent",
            "#22cc66",
            "--brand-title",
            "OPASTRO",
            "--brand-url",
            "https://opastro.com",
            "--premium-url",
            "https://numerologyapi.com",
        ]
    )
    assert code == 0
    capsys.readouterr()

    code = main(
        [
            "natal",
            "--birth-date",
            "2004-06-14",
            "--birth-time",
            "09:30",
            "--lat",
            "4.0511",
            "--lon",
            "9.7679",
            "--timezone",
            "Africa/Douala",
            "--wheel-svg",
            str(wheel_svg),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "OPASTRO NATAL REPORT" in captured.out
    assert wheel_svg.exists()
    svg = wheel_svg.read_text()
    assert "#22cc66" in svg
    assert "#1a5f45" in svg  # day theme radial gradient start
    assert "Name: Dakidarts" in svg
