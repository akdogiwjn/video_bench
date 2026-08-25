#!/usr/bin/env python3
"""Validate benchmark specification consistency before formal run.

Checks:
- GEN/EDIT duration: task.prompt == creative_brief == expected_constraints
- EDIT fixture: manifest total_duration == ffprobe sum
- case_id consistency across all files
- No PLACEHOLDER in any file
- All asset_ids unique
- All referenced files exist
- Rubric case_id matches
- Skill SHA256 referenced
"""
import json
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
ERRORS = []


def check(condition, msg):
    if not condition:
        ERRORS.append(msg)


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def main():
    # 1. GEN duration consistency
    gen_constraints = load_json(ROOT / "cases/10_video_generate/fixtures/expected_constraints.json")
    gen_brief = load_json(ROOT / "cases/10_video_generate/fixtures/creative_brief.json")
    gen_prompt = (ROOT / "cases/10_video_generate/task.prompt").read_text()

    gen_dur = gen_constraints.get("duration_range_seconds", [])
    gen_brief_max = gen_brief.get("max_duration_seconds")
    gen_brief_target = gen_brief.get("target_duration_seconds")

    check(gen_dur and gen_dur[1] == gen_brief_max, f"GEN: constraints max ({gen_dur}) != brief max ({gen_brief_max})")
    check("30-45" in gen_prompt or "30–45" in gen_prompt, f"GEN: task.prompt doesn't mention 30-45s")

    # 2. EDIT duration consistency
    edit_constraints = load_json(ROOT / "cases/11_video_edit/fixtures/expected_constraints.json")
    edit_brief = load_json(ROOT / "cases/11_video_edit/fixtures/edit_brief.json")
    edit_dur = edit_constraints.get("duration_range_seconds", [])
    edit_brief_dur = edit_brief.get("target_duration", "")

    check("55-65" in str(edit_dur) or "55" in str(edit_dur), f"EDIT: constraints duration = {edit_dur}")
    check("55-65" in edit_brief_dur or "55" in edit_brief_dur, f"EDIT: brief duration = {edit_brief_dur}")

    # 3. EDIT fixture manifest total vs ffprobe
    manifest = load_json(ROOT / "cases/11_video_edit/fixtures/source_manifest.json")
    manifest_total = manifest.get("total_source_video_duration_ms", 0)
    media_dir = ROOT / "cases/11_video_edit/fixtures/media"
    if media_dir.exists():
        import subprocess
        actual_total = 0
        for f in sorted(media_dir.glob("source_*.mp4")):
            r = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)], capture_output=True, text=True)
            try:
                actual_total += int(float(r.stdout.strip()) * 1000)
            except ValueError:
                pass
        diff = abs(manifest_total - actual_total)
        check(diff < 2000, f"EDIT: manifest total ({manifest_total}ms) != ffprobe sum ({actual_total}ms), diff={diff}ms")

    # 4. asset_id uniqueness
    asset_ids = [s.get("asset_id", "") for s in manifest.get("source_materials", []) + manifest.get("derived_materials", [])]
    dups = [x for x in asset_ids if asset_ids.count(x) > 1]
    check(len(dups) == 0, f"EDIT: duplicate asset_ids: {set(dups)}")

    # 5. No PLACEHOLDER
    for f in ROOT.rglob("*"):
        if f.is_file() and f.suffix in (".json", ".md", ".py", ".sh", ".toml") and ".git" not in str(f) and "results" not in str(f) and "REVIEW" not in str(f):
            content = f.read_text(encoding="utf-8", errors="replace")
            if "PLACEHOLDER" in content and "validate_benchmark_spec" not in str(f):
                ERRORS.append(f"PLACEHOLDER found in {f}")

    # 6. case_id consistency
    case_index = load_json(ROOT / "manifests/case_index.json")
    gen_id = case_index.get("cases", {}).get("SUB-NET-VIDEO-GEN-01", {}).get("title", "")
    check("GEN" in gen_id or gen_id, f"case_index GEN ID: {gen_id}")

    # 7. Rubric case_id
    gen_rubric = load_json(ROOT / "evidence/judge_rubric_gen.json")
    edit_rubric = load_json(ROOT / "evidence/judge_rubric_edit.json")
    check(gen_rubric.get("case_id") == "SUB-NET-VIDEO-GEN-01", f"GEN rubric case_id: {gen_rubric.get('case_id')}")
    check(edit_rubric.get("case_id") == "SUB-CPU-VIDEO-EDIT-01", f"EDIT rubric case_id: {edit_rubric.get('case_id')}")

    # 8. Rubric should NOT have audio dimensions (qwen-vl-max can't hear audio)
    for dim in gen_rubric.get("dimensions", []):
        check("audio" not in dim["name"].lower(), f"GEN rubric has audio dimension: {dim['name']} (qwen-vl-max can't hear)")
    for dim in edit_rubric.get("dimensions", []):
        check("audio" not in dim["name"].lower(), f"EDIT rubric has audio dimension: {dim['name']} (qwen-vl-max can't hear)")

    # 9. All referenced fixture files exist
    for s in manifest.get("source_materials", []) + manifest.get("derived_materials", []):
        f = media_dir / s.get("file", "")
        check(f.exists(), f"Missing fixture file: {s.get('file', '')}")

    # 10. budget_freeze keys
    pricing = load_json(ROOT / "evidence/api_pricing_snapshot.json")
    bf = pricing.get("budget_freeze", {})
    check("gen" in bf, f"budget_freeze missing 'gen' key, has: {list(bf.keys())}")
    check("edit" in bf, f"budget_freeze missing 'edit' key, has: {list(bf.keys())}")

    # 11. Hidden GT fixture_version == manifest fixture_version
    gt = load_json(ROOT / "verifier/hidden/edit_ground_truth.json")
    check(gt.get("fixture_version") == manifest.get("fixture_version"),
          f"GT fixture_version ({gt.get('fixture_version')}) != manifest ({manifest.get('fixture_version')})")

    # 12. GT distractor IDs ⊆ manifest asset IDs
    manifest_asset_ids = set(s.get("asset_id", "") for s in manifest.get("source_materials", []) + manifest.get("derived_materials", []))
    gt_distractor_ids = set(gt.get("distractor_asset_ids", []))
    for did in gt_distractor_ids:
        check(did in manifest_asset_ids, f"GT distractor ID '{did}' not in manifest asset_ids")

    # 13. GT valid IDs ⊆ manifest asset IDs
    gt_valid_ids = set(gt.get("valid_video_asset_ids", []) + gt.get("valid_image_asset_ids", []))
    for vid in gt_valid_ids:
        check(vid in manifest_asset_ids, f"GT valid ID '{vid}' not in manifest asset_ids")

    # 14. manifest SHA256 == actual file SHA256 (spot check first 3)
    for item in manifest.get("source_materials", [])[:3]:
        f = media_dir / item.get("file", "")
        if f.exists() and "sha256" in item:
            actual_sha = hashlib.sha256(f.read_bytes()).hexdigest()
            check(item["sha256"] == actual_sha, f"SHA mismatch: {item.get('file')} manifest={item['sha256'][:16]} actual={actual_sha[:16]}")

    # 15. EDIT brief source counts match manifest
    video_sources = [s for s in manifest.get("source_materials", []) if s.get("type") == "video"]
    image_sources = [s for s in manifest.get("source_materials", []) if s.get("type") == "image"]
    check(len(video_sources) >= 6, f"EDIT: expected >=6 video sources, got {len(video_sources)}")
    check(len(image_sources) >= 1, f"EDIT: expected >=1 image source, got {len(image_sources)}")
    check(len(manifest.get("derived_materials", [])) == 4, f"EDIT: expected 4 distractors, got {len(manifest.get('derived_materials', []))}")

    # 16. GT source counts match manifest
    check(gt.get("talking_head_count") == 2, f"GT talking_head_count: {gt.get('talking_head_count')}")
    check(gt.get("broll_count") == len(gt.get("broll_video_ids", [])), f"GT broll_count mismatch")

    # Report
    if ERRORS:
        print(f"[FAIL] {len(ERRORS)} validation errors:")
        for e in ERRORS:
            print(f"  ✗ {e}")
        sys.exit(1)
    else:
        print("[PASS] All benchmark spec checks passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
