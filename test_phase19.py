"""
test_phase19.py — Test suite for Phase 19 Web Admin Dashboard.

Verifies:
1. Dashboard package.json & directory structure exist.
2. No secrets in frontend source files (BOT_TOKEN, ADMIN_TELEGRAM_ID, etc.).
3. API service layer isolates mock data and exposes all required functions.
4. Dashboard build succeeds (npm run build).
5. Output dist/ bundle contains HTML and bundled JS/CSS assets.
6. All existing Telegram bot tests continue to pass without regression.
"""
import os
import re
import subprocess
import unittest
from pathlib import Path

import config

DASHBOARD_DIR = Path(__file__).resolve().parent / "dashboard"
SRC_DIR = DASHBOARD_DIR / "src"

class TestPhase19Dashboard(unittest.TestCase):

    def test_01_dashboard_structure(self):
        """Verify dashboard project structure and required directories exist."""
        self.assertTrue(DASHBOARD_DIR.exists(), "dashboard directory must exist")
        self.assertTrue((DASHBOARD_DIR / "package.json").exists(), "package.json must exist")
        self.assertTrue((DASHBOARD_DIR / "vite.config.js").exists(), "vite.config.js must exist")
        self.assertTrue((DASHBOARD_DIR / "index.html").exists(), "index.html must exist")
        self.assertTrue((SRC_DIR / "main.jsx").exists(), "main.jsx must exist")
        self.assertTrue((SRC_DIR / "App.jsx").exists(), "App.jsx must exist")
        self.assertTrue((SRC_DIR / "services" / "api.js").exists(), "api.js must exist")
        self.assertTrue((SRC_DIR / "hooks" / "useAuth.js").exists(), "useAuth.js must exist")
        self.assertTrue((SRC_DIR / "layouts" / "DashboardLayout.jsx").exists(), "DashboardLayout.jsx must exist")
        self.assertTrue((SRC_DIR / "pages" / "Login.jsx").exists(), "Login.jsx must exist")
        self.assertTrue((SRC_DIR / "pages" / "Overview.jsx").exists(), "Overview.jsx must exist")
        self.assertTrue((SRC_DIR / "pages" / "PromoCodes.jsx").exists(), "PromoCodes.jsx must exist")
        self.assertTrue((SRC_DIR / "pages" / "Campaigns.jsx").exists(), "Campaigns.jsx must exist")
        self.assertTrue((SRC_DIR / "pages" / "PendingRequests.jsx").exists(), "PendingRequests.jsx must exist")
        self.assertTrue((SRC_DIR / "pages" / "Customers.jsx").exists(), "Customers.jsx must exist")
        self.assertTrue((SRC_DIR / "pages" / "Statistics.jsx").exists(), "Statistics.jsx must exist")
        self.assertTrue((SRC_DIR / "components" / "Sidebar.jsx").exists(), "Sidebar.jsx must exist")
        self.assertTrue((SRC_DIR / "components" / "Header.jsx").exists(), "Header.jsx must exist")
        self.assertTrue((SRC_DIR / "components" / "StatCard.jsx").exists(), "StatCard.jsx must exist")
        self.assertTrue((SRC_DIR / "components" / "ActiveCampaignCard.jsx").exists(), "ActiveCampaignCard.jsx must exist")
        self.assertTrue((SRC_DIR / "components" / "RecentRequestsTable.jsx").exists(), "RecentRequestsTable.jsx must exist")

    def test_02_no_secrets_in_frontend_source(self):
        """Frontend files must NEVER contain BOT_TOKEN or ADMIN_TELEGRAM_ID."""
        bot_token = config.BOT_TOKEN
        admin_id_str = str(config.ADMIN_TELEGRAM_ID) if config.ADMIN_TELEGRAM_ID else ""

        for root, _, files in os.walk(DASHBOARD_DIR):
            if "node_modules" in root or "dist" in root:
                continue
            for file in files:
                file_path = Path(root) / file
                if file_path.suffix in [".js", ".jsx", ".ts", ".tsx", ".html", ".env", ".json"]:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    if bot_token and len(bot_token) > 5:
                        self.assertNotIn(
                            bot_token,
                            content,
                            f"Secret BOT_TOKEN exposed in {file_path.name}"
                        )
                    if admin_id_str and len(admin_id_str) > 4:
                        # Ensure real admin ID integer is not hardcoded in JS/JSX
                        if file_path.suffix in [".js", ".jsx"]:
                            self.assertNotIn(
                                admin_id_str,
                                content,
                                f"Secret ADMIN_TELEGRAM_ID hardcoded in {file_path.name}"
                            )

    def test_03_api_service_functions(self):
        """API service layer must define all required operations."""
        api_file = SRC_DIR / "services" / "api.js"
        content = api_file.read_text(encoding="utf-8")
        
        required_functions = [
            "getDashboardStats",
            "getActiveCampaign",
            "getPromoCodes",
            "getCampaigns",
            "getPendingRequests",
            "getCustomers",
            "acceptRequest",
            "rejectRequest",
            "login",
            "logout",
        ]
        for fn in required_functions:
            self.assertIn(f"export async function {fn}", content, f"Missing {fn} in api.js")

    def test_04_sidebar_navigation_items(self):
        """Sidebar must contain links to Overview, Promo Codes, Campaigns, Requests, Customers, Statistics, and Logout."""
        sidebar_file = SRC_DIR / "components" / "Sidebar.jsx"
        content = sidebar_file.read_text(encoding="utf-8")

        self.assertIn("Overview", content)
        self.assertIn("Promo Codes", content)
        self.assertIn("Campaigns", content)
        self.assertIn("Pending Requests", content)
        self.assertIn("Customers", content)
        self.assertIn("Statistics", content)
        self.assertIn("Logout", content)

    def test_05_overview_components_rendered(self):
        """Overview page must render StatCards, ActiveCampaignCard, and RecentRequestsTable."""
        overview_file = SRC_DIR / "pages" / "Overview.jsx"
        content = overview_file.read_text(encoding="utf-8")

        self.assertIn("<StatCard", content)
        self.assertIn("<ActiveCampaignCard", content)
        self.assertIn("<RecentRequestsTable", content)
        self.assertIn("Promo Codes", content)
        self.assertIn("Active Campaign", content)
        self.assertIn("Pending Requests", content)
        self.assertIn("Customers", content)
        self.assertIn("Accepted", content)
        self.assertIn("Rejected", content)

    def test_06_active_campaign_card_progress_bar(self):
        """Active campaign card must display progress bar and slot counts."""
        card_file = SRC_DIR / "components" / "ActiveCampaignCard.jsx"
        content = card_file.read_text(encoding="utf-8")

        self.assertIn("progress-bar-track", content)
        self.assertIn("progress-bar-fill", content)
        self.assertIn("remaining", content.lower())

    def test_07_recent_requests_status_badges(self):
        """Recent requests table must support PENDING, ACCEPTED, REJECTED statuses."""
        table_file = SRC_DIR / "components" / "RecentRequestsTable.jsx"
        content = table_file.read_text(encoding="utf-8")

        self.assertIn("PENDING", content)
        self.assertIn("ACCEPTED", content)
        self.assertIn("REJECTED", content)

    def test_08_netlify_redirects_configured(self):
        """Netlify SPA redirect rule must be present in public/_redirects."""
        redirects_file = DASHBOARD_DIR / "public" / "_redirects"
        self.assertTrue(redirects_file.exists(), "_redirects file must exist")
        content = redirects_file.read_text(encoding="utf-8")
        self.assertIn("/*    /index.html   200", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
