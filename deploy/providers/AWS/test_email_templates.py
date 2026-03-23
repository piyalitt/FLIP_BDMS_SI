#!/usr/bin/env python3
"""
Copyright (c) 2026 Guy's and St Thomas' NHS Foundation Trust & King's College London
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at
    http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Email Template Testing Utility for FLIP Cognito Emails

This script tests and renders email templates locally with placeholder substitution.
It validates template rendering and generates HTML preview files for manual testing.

Templates are loaded from email_templates/ directory for single source of truth between
Python testing and Terraform/HCL configuration.

Usage:
    python3 test_email_templates.py                    # Test all templates
    python3 test_email_templates.py --output-dir ./previews  # Save to custom directory
    python3 test_email_templates.py --serve           # Start local HTTP server for preview
"""

import argparse
import os
from dataclasses import dataclass
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Dict, Optional


@dataclass
class TestUser:
    """Test user data for email template substitution."""

    username: str = "john.smith@example.com"
    temp_password: str = "TempP@ss123456"
    verification_code: str = "789456"
    subdomain: str = "flip-staging.example.com"
    reset_link: str = "https://flip-staging.example.com/reset?token=abc123xyz789"


class EmailTemplateTester:
    """Tests and renders FLIP Cognito email templates loaded from files."""

    def __init__(self, test_user: Optional[TestUser] = None):
        """Initialize the tester with test user data and load templates from files.
        
        Templates are loaded from email_templates/ directory. This ensures Python
        and Terraform reference the same source files, preventing drift.
        """
        self.test_user = test_user or TestUser()
        
        # Load templates from files (single source of truth)
        template_dir = Path(__file__).parent / "email_templates"
        self.INVITE_TEMPLATE_HTML = (template_dir / "invite.html").read_text()
        self.PASSWORD_RESET_CODE_TEMPLATE_HTML = (template_dir / "password_reset_code.html").read_text()
        self.PASSWORD_RESET_LINK_TEMPLATE_HTML = (template_dir / "password_reset_link.html").read_text()

    def substitute_placeholders(self, template: str) -> tuple[str, Dict[str, str]]:
        """
        Substitute Cognito placeholders in email template.

        Returns:
            Tuple of (rendered_html, substitutions_dict)
        """
        substitutions = {
            "{username}": self.test_user.username,
            "{####}": self.test_user.verification_code,
            "{flip_alb_subdomain}": self.test_user.subdomain,
            "{reset_link}": self.test_user.reset_link,
        }

        rendered = template
        for placeholder, value in substitutions.items():
            rendered = rendered.replace(placeholder, value)

        return rendered, substitutions

    def validate_template(self, template: str, template_name: str) -> Dict[str, any]:
        """
        Validate email template for common issues.

        Args:
            template: HTML template string
            template_name: Name of template for reporting

        Returns:
            Validation report with issues and warnings
        """
        issues = []
        warnings = []

        # Check for missing DOCTYPE
        if "<!DOCTYPE html>" not in template:
            warnings.append("Missing DOCTYPE declaration")

        # Check for meta charset
        if 'charset="utf-8"' not in template:
            warnings.append("Missing UTF-8 charset declaration")

        # Check for viewport meta tag
        if "viewport" not in template:
            warnings.append("Missing viewport meta tag (may not render well on mobile)")

        # Check for FLIP branding
        if "#61366e" not in template or "#9452A8" not in template:
            issues.append("Missing FLIP primary color (#61366e or #9452A8)")

        # Check for inline CSS
        if "<style>" in template or "<link rel=" in template:
            warnings.append("Using external stylesheets - inline CSS preferred for email compatibility")

        # Check for table-based layout
        if "<table" not in template:
            warnings.append("Not using table-based layout - may have rendering issues in some email clients")

        # Check for required text elements
        required_text = ["FLIP", "The FLIP Team", "Hello"]
        for text in required_text:
            if text not in template:
                issues.append(f"Missing required text: '{text}'")

        # Validate accessibility
        if "<alt=" not in template and "<img" in template:
            warnings.append("Images present without alt text")

        return {
            "template": template_name,
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "total_chars": len(template),
            "estimated_size_kb": len(template) / 1024,
        }

    def render_and_save(self, output_dir: Path) -> None:
        """
        Render all templates with placeholders and save to HTML files.

        Args:
            output_dir: Directory to save HTML preview files
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        templates = [
            ("invite", self.INVITE_TEMPLATE_HTML),
            ("password_reset_code", self.PASSWORD_RESET_CODE_TEMPLATE_HTML),
            ("password_reset_link", self.PASSWORD_RESET_LINK_TEMPLATE_HTML),
        ]

        for name, template in templates:
            rendered, subs = self.substitute_placeholders(template)

            # Create preview HTML with metadata
            preview = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>FLIP Email - {name.replace("_", " ").title()}</title>
    <style>
        body {{ font-family: system-ui, sans-serif; background: #f0f0f0; margin: 0; padding: 20px; }}
        .metadata {{ background: #fff; padding: 20px; margin-bottom: 20px; border-radius: 4px; border-left: 4px solid #61366e; }}
        .metadata h2 {{ margin: 0 0 10px 0; color: #301A37; }}
        .metadata p {{ margin: 5px 0; color: #666; font-size: 14px; }}
        .metadata code {{ background: #f5f5f5; padding: 2px 6px; border-radius: 3px; font-family: monospace; }}
        .email-preview {{ background: #fff; border-radius: 4px; overflow: hidden; }}
        .test-info {{ background: #FEF3F2; padding: 10px 20px; border-top: 1px solid #E51170; color: #BF360C; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="metadata">
        <h2>FLIP Email Template Preview</h2>
        <p><strong>Type:</strong> {name.replace("_", " ").title()}</p>
        <p><strong>Size:</strong> {len(rendered) / 1024:.1f} KB</p>
        <p><strong>Test User:</strong> {self.test_user.username}</p>
        <p><strong>Environment:</strong> {self.test_user.subdomain}</p>
        <hr>
        <p><strong>Substitutions Applied:</strong></p>
        <ul>
"""
            for placeholder, value in subs.items():
                preview += f"            <li><code>{placeholder}</code> → <code>{value}</code></li>\n"

            preview += f"""        </ul>
    </div>
    <div class="email-preview">
        {rendered}
    </div>
    <div class="test-info">
        Open this file in your email client or upload to Litmus/Email-on-Acid for cross-client testing.
    </div>
</body>
</html>
"""

            output_file = output_dir / f"flip_email_{name}.html"
            output_file.write_text(preview)
            print(f"✓ Saved: {output_file}")

    def test_all(self) -> list[Dict]:
        """Run all validation tests.
        
        Returns:
            List of test results for each template
        """
        templates = [
            ("Temporary Password Invitation", self.INVITE_TEMPLATE_HTML),
            ("Password Reset (Code)", self.PASSWORD_RESET_CODE_TEMPLATE_HTML),
            ("Password Reset (Link)", self.PASSWORD_RESET_LINK_TEMPLATE_HTML),
        ]

        results = []
        for name, template in templates:
            validation = self.validate_template(template, name)
            rendered, subs = self.substitute_placeholders(template)

            results.append({
                "name": name,
                "validation": validation,
                "substitutions": subs,
                "rendered_size_kb": len(rendered) / 1024,
            })

        return results


def print_test_results(results: list) -> None:
    """Pretty-print test results."""
    print("\n" + "=" * 80)
    print("FLIP EMAIL TEMPLATE VALIDATION REPORT".center(80))
    print("=" * 80 + "\n")

    for result in results:
        name = result["name"]
        validation = result["validation"]

        status = "✓ PASS" if validation["valid"] else "✗ FAIL"
        print(f"{status} | {name}")
        print(f"  Size: {result['rendered_size_kb']:.1f} KB")

        if validation["issues"]:
            print("  Issues:")
            for issue in validation["issues"]:
                print(f"    ✗ {issue}")

        if validation["warnings"]:
            print("  Warnings:")
            for warning in validation["warnings"]:
                print(f"    ⚠ {warning}")

        print()

    print("=" * 80)
    print(f"Total templates tested: {len(results)}")
    passed = sum(1 for r in results if r["validation"]["valid"])
    print(f"Passed: {passed}/{len(results)}")
    print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Test FLIP Cognito email templates locally")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./email_previews"),
        help="Directory to save HTML preview files (default: ./email_previews)",
    )
    parser.add_argument(
        "--username",
        default="john.smith@example.com",
        help="Test username to substitute (default: john.smith@example.com)",
    )
    parser.add_argument(
        "--subdomain",
        default="flip-staging.example.com",
        help="FLIP subdomain to substitute (default: flip-staging.example.com)",
    )
    parser.add_argument(
        "--serve", action="store_true", help="Start local HTTP server to view previews (default port: 8000)"
    )
    parser.add_argument("--port", type=int, default=8000, help="Port for local HTTP server (default: 8000)")

    args = parser.parse_args()

    # Create test user with provided arguments
    test_user = TestUser(username=args.username, subdomain=args.subdomain)

    # Run tests
    tester = EmailTemplateTester(test_user)
    results = tester.test_all()
    print_test_results(results)

    # Save previews
    print(f"\nSaving email previews to: {args.output_dir.absolute()}")
    tester.render_and_save(args.output_dir)

    # Optionally serve previews
    if args.serve:
        print(f"\n📧 Starting local HTTP server at http://localhost:{args.port}")
        print("Open the following URLs in your browser:")
        for name in ["invite", "password_reset_code", "password_reset_link"]:
            print(f"  • http://localhost:{args.port}/flip_email_{name}.html")
        print("\nPress Ctrl+C to stop the server.\n")

        os.chdir(args.output_dir)
        handler = SimpleHTTPRequestHandler
        server = HTTPServer(("localhost", args.port), handler)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n\nServer stopped.")


if __name__ == "__main__":
    main()
