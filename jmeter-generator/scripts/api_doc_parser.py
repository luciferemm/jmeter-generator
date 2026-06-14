"""
API Documentation Parser for JMeter script generation.

Scans the input/ folder for API documentation files, parses them
into ScriptConfig JSON compatible with jmx_builder.py, and generates
JMeter (.jmx) scripts into the output/ folder.

Supported formats:
  - Markdown (.md) — structured API docs with Method/URL/Headers/Body
  - JSON (.json) — single interface, array of interfaces, or full ScriptConfig
  - YAML (.yaml/.yml) — same structures as JSON
  - OpenAPI / Swagger (.json/.yaml) — full spec parsing
  - HAR (.har) — HTTP Archive files (delegates to har_parser.py)

Usage:
    # Parse all docs in input/ → generate config JSON
    python api_doc_parser.py --input-dir input/ --output-config merged_config.json

    # Parse + generate JMX in one step
    python api_doc_parser.py --input-dir input/ --output-dir output/ --generate

    # Parse specific files
    python api_doc_parser.py --files api1.md api2.json --output-config merged.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

SUPPORTED_EXTENSIONS = {".md", ".json", ".yaml", ".yml", ".har"}

HTTP_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}

# ──────────────────────────────────────────────
# Markdown Parser
# ──────────────────────────────────────────────

# Match "## 接口1：用户登录" or "## Login" or "### POST /login"
SECTION_PATTERN = re.compile(
    r"^(#{1,4})\s*(?:接口\d*\s*[：:]\s*)?(.+?)(?:\s*[：:]\s*(.+))?$",
    re.MULTILINE,
)

# Match "- **Method**: POST" or "- Method: GET"
METHOD_PATTERN = re.compile(
    r"(?:[-*]\s*)?\*{0,2}Method\*{0,2}\s*[：:]\s*(\w+)", re.IGNORECASE
)

# Match "- **URL**: https://..." or full URL
URL_PATTERN = re.compile(
    r"(?:[-*]\s*)?\*{0,2}URL\*{0,2}\s*[：:]\s*(https?://\S+)", re.IGNORECASE
)

# Full URL with method: "POST https://api.example.com/login"
METHOD_URL_PATTERN = re.compile(
    r"(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+(https?://\S+)", re.IGNORECASE
)

# Header line: "- Content-Type: application/json"
HEADER_PATTERN = re.compile(
    r"(?:[-*]\s+)([\w-]+)\s*[：:]\s*(.+)"
)

# Code block for body
CODE_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)

# Inline body: Body: {"key":"value"}
BODY_PATTERN = re.compile(
    r"(?:[-*]\s*)?\*{0,2}(?:Body|请求体|Payload)\*{0,2}\s*[：:]\s*(\{.+?\}|<.+?>|.+?)(?:\n|$)",
    re.IGNORECASE,
)

# Query params: "- page: 1" after a "Query Parameters:" section
QUERY_PARAM_PATTERN = re.compile(
    r"(?:[-*]\s+)(\w+)\s*[=：:]\s*(\S+)"
)


def parse_markdown_api_doc(text: str) -> list[dict]:
    """Parse a Markdown API documentation file into a list of ApiInterface dicts."""
    interfaces = []

    # Strategy: find all METHOD URL pairs first (most reliable)
    method_url_matches = list(METHOD_URL_PATTERN.finditer(text))

    # If no METHOD URL pairs found, look for structured sections
    if not method_url_matches:
        interfaces = _parse_markdown_sections(text)
        if interfaces:
            return interfaces
        # Fallback: try to find method and URL separately
        interfaces = _parse_markdown_loose(text)
        return interfaces

    # Process each METHOD URL pair
    for match in method_url_matches:
        method = match.group(1).upper()
        url = match.group(2)
        start = match.end()

        # Find the next match or EOF
        next_match = None
        for m in method_url_matches:
            if m.start() > match.start():
                next_match = m
                break

        end = next_match.start() if next_match else len(text)
        block = text[start:end]

        iface = _extract_interface_from_block(method, url, block)
        interfaces.append(iface)

    return interfaces


def _parse_markdown_sections(text: str) -> list[dict]:
    """Parse markdown with ## section headers for each API."""
    interfaces = []

    # Find all ## sections that might describe APIs
    sections = re.split(r"^#{1,3}\s+", text, flags=re.MULTILINE)

    for section in sections[1:]:  # Skip pre-first-header content
        # Try to find method+url in this section
        m = METHOD_URL_PATTERN.search(section)
        if m:
            method = m.group(1).upper()
            url = m.group(2)
            iface = _extract_interface_from_block(method, url, section)
            interfaces.append(iface)
            continue

        # Try separate method and URL lines
        method_m = METHOD_PATTERN.search(section)
        url_m = URL_PATTERN.search(section)
        if method_m and url_m:
            method = method_m.group(1).upper()
            url = url_m.group(1)
            iface = _extract_interface_from_block(method, url, section)
            interfaces.append(iface)

    return interfaces


def _parse_markdown_loose(text: str) -> list[dict]:
    """Last-resort parse: look for method and URL lines anywhere."""
    interfaces = []

    # Find all URLs
    url_matches = list(re.finditer(r"https?://[^\s)\]]+", text))
    method_matches = list(re.finditer(
        r"(?:^|\n)\s*(?:[-*]\s*)?\*{0,2}Method\*{0,2}\s*[：:]\s*(\w+)",
        text, re.IGNORECASE
    ))

    if not url_matches:
        return interfaces

    for i, url_match in enumerate(url_matches):
        url = url_match.group(0).rstrip(".,;")
        # Try to find the closest method spec before this URL
        method = "GET"
        for mm in method_matches:
            if mm.end() <= url_match.start():
                method = mm.group(1).upper()
        iface = _extract_interface_from_block(method, url, text)
        interfaces.append(iface)
        if i >= 20:  # Safety cap
            break

    return interfaces


def _extract_interface_from_block(method: str, url: str, block: str) -> dict:
    """Extract headers, body, query params from a text block."""
    from urllib.parse import urlparse, parse_qs

    parsed = urlparse(url)
    protocol = parsed.scheme.upper() if parsed.scheme else "HTTPS"
    host = parsed.hostname or ""
    port = parsed.port
    path = parsed.path or "/"

    # Extract query params from URL
    query_params = []
    if parsed.query:
        query_params = [
            {"name": k, "value": v[0]}
            for k, v in parse_qs(parsed.query).items()
        ]

    # Find headers in block
    headers = []
    # Look for header lines under a "Headers" context
    header_section_match = re.search(
        r"(?:Headers|请求头|请求Header)\s*[：:]?\s*\n(.+?)(?:\n\n|\n#|\n(?:Body|请求体|Query|查询参数)|\Z)",
        block, re.DOTALL | re.IGNORECASE
    )
    header_block = header_section_match.group(1) if header_section_match else block

    for h_match in HEADER_PATTERN.finditer(header_block):
        hname = h_match.group(1).strip()
        hvalue = h_match.group(2).strip()
        # Filter out non-header keys
        if hname.lower() not in {"method", "url", "body", "请求体", "请求地址"}:
            headers.append({"name": hname, "value": hvalue})

    # Find body
    body = None
    # Try code block first
    code_match = CODE_BLOCK_PATTERN.search(block)
    if code_match:
        raw = code_match.group(1).strip()
        body = {"type": "json", "content": raw}
    else:
        # Try inline body
        body_m = BODY_PATTERN.search(block)
        if body_m:
            raw = body_m.group(1).strip()
            body = {"type": "json", "content": raw}

    # Name: derive from method + path
    name = f"{method} {path}"

    iface = {
        "name": name,
        "method": method,
        "protocol": protocol,
        "host": host,
        "path": path,
        "headers": headers,
        "query_params": query_params,
    }

    if port:
        iface["port"] = port
    if body:
        iface["body"] = body

    return iface


# ──────────────────────────────────────────────
# JSON / YAML Parser
# ──────────────────────────────────────────────

def parse_json_config(data: dict) -> dict:
    """Parse a JSON/YAML object into a dict of {interfaces, test_name?, scenario?}.

    Accepts:
      - Full ScriptConfig: {"test_name": ..., "api_interfaces": [...], "scenario": ...}
      - Array of ApiInterfaces: [{"name": ..., "method": ...}, ...]
      - Single ApiInterface: {"name": ..., "method": ...}

    Returns a dict with keys:
      - interfaces: list of ApiInterface dicts
      - test_name: str or None
      - scenario: dict or None
    """
    # Full ScriptConfig
    if "api_interfaces" in data:
        return {
            "interfaces": data["api_interfaces"],
            "test_name": data.get("test_name"),
            "scenario": data.get("scenario"),
        }

    # Array of interfaces
    if isinstance(data, list):
        return {"interfaces": data, "test_name": None, "scenario": None}

    # Single interface
    if isinstance(data, dict) and "method" in data:
        return {"interfaces": [data], "test_name": None, "scenario": None}

    raise ValueError(
        "JSON/YAML must be a ScriptConfig, an array of ApiInterfaces, "
        "or a single ApiInterface object"
    )


# ──────────────────────────────────────────────
# OpenAPI / Swagger Parser
# ──────────────────────────────────────────────

def parse_openapi_spec(spec: dict) -> list[dict]:
    """Parse an OpenAPI 3.x or Swagger 2.x specification."""
    interfaces = []

    openapi_version = spec.get("openapi") or spec.get("swagger", "unknown")
    servers = spec.get("servers", [])
    base_url = ""
    if servers:
        server_0 = servers[0] if isinstance(servers[0], str) else servers[0].get("url", "")
        base_url = server_0.rstrip("/")

    # Swagger 2.x compatibility
    if not base_url:
        host = spec.get("host", "")
        base_path = spec.get("basePath", "")
        schemes = spec.get("schemes", ["https"])
        if host:
            base_url = f"{schemes[0]}://{host}{base_path}"

    paths = spec.get("paths", {})

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue

        for method_name in HTTP_METHODS:
            method_name_lower = method_name.lower()
            operation = path_item.get(method_name_lower)
            if not operation:
                continue

            # Build URL
            full_url = _build_openapi_url(base_url, path, operation, spec)

            # Extract headers
            headers = _extract_openapi_headers(operation, spec)

            # Extract body
            body = _extract_openapi_body(operation)

            # Extract query parameters
            query_params = _extract_openapi_query_params(operation, spec, path_item)

            interface_name = operation.get("summary") or operation.get("operationId") or f"{method_name.upper()} {path}"
            protocol = "HTTPS" if "https" in base_url else "HTTP"
            parsed = __import__("urllib.parse").parse.urlparse(full_url)
            host = parsed.hostname or ""
            port = parsed.port

            iface = {
                "name": interface_name,
                "method": method_name.upper(),
                "protocol": protocol,
                "host": host,
                "path": parsed.path or "/",
                "headers": headers,
                "query_params": query_params,
            }

            if port:
                iface["port"] = port
            if body:
                iface["body"] = body

            interfaces.append(iface)

    return interfaces


def _build_openapi_url(base_url: str, path: str, operation: dict, spec: dict) -> str:
    """Build the full URL for an OpenAPI operation."""
    # Check operation-level servers (OpenAPI 3.x)
    op_servers = operation.get("servers", [])
    if op_servers:
        s = op_servers[0]
        if isinstance(s, str):
            base_url = s.rstrip("/")
        else:
            base_url = s.get("url", base_url).rstrip("/")
    return f"{base_url}{path}"


def _extract_openapi_headers(operation: dict, spec: dict) -> list[dict]:
    """Extract headers from OpenAPI operation parameters."""
    headers = []
    parameters = operation.get("parameters", [])

    for param in parameters:
        if isinstance(param, dict) and param.get("in") == "header":
            hname = param["name"]
            # Try to get example/default value
            example = ""
            if "example" in param:
                example = str(param["example"])
            elif "schema" in param and "example" in param["schema"]:
                example = str(param["schema"]["example"])
            elif "schema" in param and "default" in param["schema"]:
                example = str(param["schema"]["default"])
            headers.append({"name": hname, "value": example})

    # Also check security schemes for Authorization headers
    security = operation.get("security", [])
    if security:
        for sec_req in security:
            if isinstance(sec_req, dict):
                for sec_name in sec_req:
                    sec_scheme = (
                        spec.get("components", {})
                        .get("securitySchemes", {})
                        .get(sec_name, {})
                    )
                    if sec_scheme.get("type") == "http" and sec_scheme.get("scheme") == "bearer":
                        headers.append({
                            "name": "Authorization",
                            "value": "Bearer ${token}"
                        })

    return headers


def _extract_openapi_body(operation: dict) -> Optional[dict]:
    """Extract request body from OpenAPI operation."""
    request_body = operation.get("requestBody", {})
    if not request_body:
        return None

    content = request_body.get("content", {})
    json_content = content.get("application/json", {})
    if json_content:
        example = json_content.get("example", {})
        if example:
            return {"type": "json", "content": json.dumps(example, ensure_ascii=False)}
        # Try schema example
        schema = json_content.get("schema", {})
        if "example" in schema:
            return {"type": "json", "content": json.dumps(schema["example"], ensure_ascii=False)}

    return None


def _extract_openapi_query_params(
    operation: dict, spec: dict, path_item: dict
) -> list[dict]:
    """Extract query parameters from OpenAPI operation."""
    query_params = []

    # Operation-level parameters
    parameters = operation.get("parameters", [])
    # Also check path-level parameters (shared params)
    path_params = path_item.get("parameters", [])
    all_params = path_params + parameters

    for param in all_params:
        if isinstance(param, dict) and param.get("in") == "query":
            pname = param["name"]
            example = ""
            if "example" in param:
                example = str(param["example"])
            elif "schema" in param and "example" in param["schema"]:
                example = str(param["schema"]["example"])
            query_params.append({"name": pname, "value": example})

    return query_params


# ──────────────────────────────────────────────
# File Scanner & Orchestrator
# ──────────────────────────────────────────────

def read_yaml_file(filepath: str) -> dict:
    """Read a YAML file, trying both PyYAML and a basic fallback."""
    try:
        import yaml  # type: ignore
        with open(filepath, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except ImportError:
        pass

    # Fallback for simple YAML without dependencies
    # This handles the subset used in OpenAPI specs
    import ast
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    # Try JSON first (valid YAML is valid JSON)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    raise ImportError(
        "PyYAML is required to parse YAML files. Install with: pip install pyyaml"
    )


def detect_format(filepath: str) -> str:
    """Detect the format of an API documentation file."""
    ext = Path(filepath).suffix.lower()

    if ext == ".md":
        return "markdown"
    elif ext == ".json":
        return "json"
    elif ext in (".yaml", ".yml"):
        return "yaml"
    elif ext == ".har":
        return "har"
    else:
        raise ValueError(f"Unsupported file extension: {ext}")


def parse_file(filepath: str) -> dict:
    """Parse a single API documentation file into {interfaces: list, test_name, scenario}."""
    fmt = detect_format(filepath)

    if fmt == "markdown":
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        return {"interfaces": parse_markdown_api_doc(content), "test_name": None, "scenario": None}

    elif fmt == "json":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return parse_json_or_openapi(data)

    elif fmt == "yaml":
        data = read_yaml_file(filepath)
        return parse_json_or_openapi(data)

    elif fmt == "har":
        # Delegate to har_parser
        print(f"  -> HAR file detected: {filepath}")
        print(f"     Use har_parser.py for HAR files: "
              f"python scripts/har_parser.py --har {filepath}")
        return {"interfaces": [], "test_name": None, "scenario": None}

    return {"interfaces": [], "test_name": None, "scenario": None}


def parse_json_or_openapi(data: dict) -> dict:
    """Detect whether data is OpenAPI/Swagger or plain config, then parse.

    Returns a dict: {interfaces: list, test_name: str|None, scenario: dict|None}
    """
    # OpenAPI 3.x or Swagger 2.x detection
    if "openapi" in data or "swagger" in data:
        return {"interfaces": parse_openapi_spec(data), "test_name": None, "scenario": None}
    return parse_json_config(data)


def scan_input_dir(input_dir: str) -> list[str]:
    """Scan input directory for supported API doc files, sorted."""
    files = []
    input_path = Path(input_dir)
    if not input_path.exists():
        print(f"Warning: Input directory not found: {input_dir}", file=sys.stderr)
        return files

    for fpath in sorted(input_path.iterdir()):
        if fpath.is_file() and fpath.suffix.lower() in SUPPORTED_EXTENSIONS:
            # Skip generated config files
            if fpath.name.endswith("_config.json"):
                continue
            files.append(str(fpath))

    return files


def merge_interfaces(all_interfaces: list[dict]) -> list[dict]:
    """Deduplicate interfaces by (method, host, path, query_params)."""
    seen = set()
    result = []
    for iface in all_interfaces:
        key = (
            iface.get("method", ""),
            iface.get("host", ""),
            iface.get("path", ""),
            json.dumps(iface.get("query_params", []), sort_keys=True),
        )
        if key not in seen:
            seen.add(key)
            result.append(iface)
    return result


def build_script_config(
    interfaces: list[dict],
    test_name: str = "",
    scenario_overrides: dict = None,
) -> dict:
    """Build a full ScriptConfig from parsed interfaces."""
    if not test_name:
        test_name = f"Auto Generated Test ({len(interfaces)} APIs)"

    scenario = {
        "threads": 10,
        "ramp_up": 10,
        "duration": 60,
        "loops": None,
        "assertions": [
            {"type": "status_code", "condition": "equals", "expected": "200"}
        ],
        "variables": [],
        "csv_data": None,
    }

    if scenario_overrides:
        scenario.update(scenario_overrides)

    return {
        "test_name": test_name,
        "api_interfaces": interfaces,
        "scenario": scenario,
    }


def process_input_dir(
    input_dir: str,
    output_config: str = None,
    output_dir: str = None,
    generate: bool = False,
    test_name: str = "",
    scenario_file: str = None,
) -> dict:
    """
    Main orchestrator: scan input/, parse all files, merge, optionally generate JMX.

    Returns the merged ScriptConfig dict.
    """
    # 1. Scan
    files = scan_input_dir(input_dir)
    if not files:
        print("No API documentation files found in input/ folder.")
        print(f"Supported formats: {', '.join(SUPPORTED_EXTENSIONS)}")
        print("Place your API docs in the input/ folder and try again.")
        sys.exit(1)

    print(f"\n{'='*50}")
    print(f"  [*] Found {len(files)} API doc file(s) in {input_dir}/")
    print(f"{'='*50}")

    # 2. Parse
    all_interfaces = []
    parsed_test_name = test_name
    parsed_scenario = None
    for fpath in files:
        fname = Path(fpath).name
        fmt = detect_format(fpath)
        print(f"\n  [>] Parsing: {fname}  [{fmt}]")
        try:
            result = parse_file(fpath)
            interfaces = result.get("interfaces", [])
            if interfaces:
                print(f"     OK Extracted {len(interfaces)} interface(s)")
                all_interfaces.extend(interfaces)
                # Use test_name from first file that provides one
                if not parsed_test_name and result.get("test_name"):
                    parsed_test_name = result["test_name"]
                # Use scenario from first file that provides one
                if not parsed_scenario and result.get("scenario"):
                    parsed_scenario = result["scenario"]
            else:
                print(f"     !! No interfaces found")
        except Exception as e:
            print(f"     XX Error: {e}")

    if not all_interfaces:
        print("\n!! No interfaces could be extracted from the input files.")
        print("  Check that your API docs follow the expected format.")
        print("  See input/example_api_doc.md for an example.")
        sys.exit(1)

    # 3. Deduplicate
    merged = merge_interfaces(all_interfaces)

    # 4. Load scenario overrides if provided
    scenario_overrides = None
    if scenario_file and os.path.isfile(scenario_file):
        with open(scenario_file, "r", encoding="utf-8") as f:
            scenario_overrides = json.load(f)

    # 5. Build config (file scenario takes precedence over parsed scenario)
    if scenario_overrides:
        parsed_scenario = scenario_overrides
    config = build_script_config(merged, test_name=parsed_test_name or test_name,
                                 scenario_overrides=parsed_scenario)

    # 6. Print summary
    print(f"\n{'='*50}")
    print(f"  --- Parse Summary ---")
    print(f"{'='*50}")
    print(f"  Total files scanned: {len(files)}")
    print(f"  Raw interfaces:      {len(all_interfaces)}")
    print(f"  Unique interfaces:   {len(merged)}")
    print(f"  Test name:           {config['test_name']}")
    print(f"{'='*50}")

    # Print interface list
    print(f"\n  Interfaces:")
    for i, iface in enumerate(merged, 1):
        body_hint = ""
        if iface.get("body"):
            body_len = len(iface["body"].get("content", ""))
            body_hint = f" [body: {body_len} chars]"
        print(f"    {i}. {iface['method']:6s} {iface.get('protocol', 'HTTPS')}://{iface['host']}{iface['path']}{body_hint}")

    # 7. Save config
    if output_config:
        output_path = Path(output_config)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_config, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"\n  OK Config written to: {output_config}")

    # 8. Generate JMX
    if generate and output_dir:
        return _generate_jmx(config, output_dir)

    return config


def _generate_jmx(config: dict, output_dir: str) -> dict:
    """Generate JMX files by calling jmx_builder."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Generate filename
    import time
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r"[^\w\s-]", "", config.get("test_name", "test"))
    safe_name = re.sub(r"[-\s]+", "_", safe_name).strip("_")
    jmx_filename = f"{safe_name}_{timestamp}.jmx"
    jmx_path = output_path / jmx_filename

    # Save temp config
    temp_config = output_path / f"_temp_config_{timestamp}.json"
    with open(temp_config, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    # Call jmx_builder
    script_dir = Path(__file__).parent
    builder_script = script_dir / "jmx_builder.py"

    import subprocess
    cmd = [
        sys.executable,
        str(builder_script),
        "--config", str(temp_config),
        "--output", str(jmx_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"  XX JMX generation failed: {result.stderr}")
        if temp_config.exists():
            temp_config.unlink()
        return config

    print(f"\n{'='*50}")
    print(f"  *** JMeter Script Generated! ***")
    print(f"{'='*50}")
    print(f"  File: {jmx_path}")
    print(f"  Size: {jmx_path.stat().st_size:,} bytes")
    print(f"{'='*50}")
    print(f"\n  Execute with JMeter:")
    print(f"     jmeter -n -t {jmx_path} -l results.jtl")
    print(f"\n  Or open in JMeter GUI:")
    print(f"     jmeter -t {jmx_path}")

    # Clean up temp config
    if temp_config.exists():
        temp_config.unlink()

    return config


# ──────────────────────────────────────────────
# CLI Entry Point
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Parse API documentation files and generate JMeter scripts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan input/ folder, save merged config
  python api_doc_parser.py --input-dir input/ --output-config merged.json

  # Scan input/ folder, generate JMX directly into output/
  python api_doc_parser.py --input-dir input/ --output-dir output/ --generate

  # Parse specific files
  python api_doc_parser.py --files api1.md api2.json --output-config merged.json

  # With custom test name and scenario overrides
  python api_doc_parser.py --input-dir input/ --output-dir output/ --generate \\
      --test-name "Login + Profile Test" --scenario scenario.json
        """,
    )
    parser.add_argument(
        "--input-dir", default="input/",
        help="Directory containing API doc files (default: input/)"
    )
    parser.add_argument(
        "--output-config",
        help="Path to save the merged ScriptConfig JSON"
    )
    parser.add_argument(
        "--output-dir", default="output/",
        help="Directory for generated JMX files (default: output/)"
    )
    parser.add_argument(
        "--generate", action="store_true",
        help="Generate JMX script after parsing"
    )
    parser.add_argument(
        "--files", nargs="+",
        help="Specific API doc files to parse (instead of scanning input-dir)"
    )
    parser.add_argument(
        "--test-name", default="",
        help="Custom test plan name"
    )
    parser.add_argument(
        "--scenario", default=None,
        help="Path to scenario override JSON (threads, duration, assertions, etc.)"
    )
    args = parser.parse_args()

    # If specific files provided, parse only those
    if args.files:
        all_interfaces = []
        parsed_test_name = args.test_name
        parsed_scenario = None
        for fpath in args.files:
            if not os.path.isfile(fpath):
                print(f"Warning: File not found, skipping: {fpath}", file=sys.stderr)
                continue
            fname = Path(fpath).name
            fmt = detect_format(fpath)
            print(f"\n  [>] Parsing: {fname}  [{fmt}]")
            try:
                result = parse_file(fpath)
                interfaces = result.get("interfaces", [])
                if interfaces:
                    print(f"     OK Extracted {len(interfaces)} interface(s)")
                    all_interfaces.extend(interfaces)
                    if not parsed_test_name and result.get("test_name"):
                        parsed_test_name = result["test_name"]
                    if not parsed_scenario and result.get("scenario"):
                        parsed_scenario = result["scenario"]
                else:
                    print(f"     !! No interfaces found")
            except Exception as e:
                print(f"     XX Error: {e}")

        if not all_interfaces:
            print("\n!! No interfaces could be extracted.")
            sys.exit(1)

        merged = merge_interfaces(all_interfaces)
        scenario_overrides = None
        if args.scenario and os.path.isfile(args.scenario):
            with open(args.scenario, "r", encoding="utf-8") as f:
                scenario_overrides = json.load(f)
        # Command-line scenario overrides parsed scenario
        if scenario_overrides:
            parsed_scenario = scenario_overrides

        config = build_script_config(merged, test_name=parsed_test_name,
                                     scenario_overrides=parsed_scenario)

        if args.output_config:
            with open(args.output_config, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            print(f"\n  OK Config written to: {args.output_config}")

        if args.generate:
            _generate_jmx(config, args.output_dir)
        return

    # Default: scan input_dir
    input_dir = args.input_dir
    output_config = args.output_config or (
        os.path.join(input_dir, "_merged_config.json") if not args.generate else None
    )

    process_input_dir(
        input_dir=input_dir,
        output_config=output_config,
        output_dir=args.output_dir,
        generate=args.generate,
        test_name=args.test_name,
        scenario_file=args.scenario,
    )


if __name__ == "__main__":
    main()
