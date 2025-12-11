"""
Report Generator per R07 Analytics
Genera report in formato Markdown e HTML

R07 - Sistema Analytics
Created: 2025-12-08

Formati:
- Markdown: per chat e notifiche
- HTML: per dashboard e export
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Generatore report analytics.
    
    Features:
    - Report Markdown per chat
    - Report HTML con grafici placeholder
    - Summary giornaliero/settimanale
    - Export per Admin Panel
    
    Example:
        >>> generator = ReportGenerator()
        >>> md_report = generator.generate_daily_markdown(data)
        >>> html_report = generator.generate_daily_html(data)
    """
    
    def __init__(self, output_dir: str = "data/reports"):
        """
        Inizializza generator.
        
        Args:
            output_dir: Directory per salvataggio report
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"ReportGenerator: output_dir={output_dir}")
    
    # ═══════════════════════════════════════════════════════════════
    # MARKDOWN REPORTS
    # ═══════════════════════════════════════════════════════════════
    
    def generate_daily_markdown(self, data: Dict[str, Any]) -> str:
        """
        Genera report giornaliero in Markdown.
        
        Args:
            data: Dict con usage, quality, glossary, memory, pipeline
            
        Returns:
            String Markdown
        """
        date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
        usage = data.get('usage', {})
        quality = data.get('quality', {})
        glossary = data.get('glossary', {})
        pipeline = data.get('pipeline', {})
        
        lines = [
            f"# 📊 Report Analytics - {date}",
            "",
            "---",
            "",
            "## 📈 Utilizzo",
            "",
            f"| Metrica | Valore |",
            f"|---------|--------|",
            f"| Query totali | {usage.get('total_queries', 0)} |",
            f"| Utenti attivi | {usage.get('unique_users', 0)} |",
        ]
        
        # Trend
        trend = usage.get('trend', {})
        if trend.get('pct_change') is not None:
            delta = trend['pct_change']
            arrow = "📈" if delta > 0 else "📉" if delta < 0 else "➡️"
            lines.append(f"| Trend | {arrow} {delta:+.1f}% vs periodo precedente |")
        
        lines.extend([
            "",
            "---",
            "",
            "## ✅ Qualità",
            "",
        ])
        
        # Health score
        health = quality.get('overall_health', {})
        score = health.get('score', 0)
        status = health.get('status', 'unknown')
        
        status_emoji = {
            'excellent': '🟢',
            'good': '🟢',
            'fair': '🟡',
            'needs_attention': '🟠',
            'critical': '🔴'
        }.get(status, '⚪')
        
        lines.extend([
            f"**Health Score**: {status_emoji} {score}/100 ({status})",
            "",
            f"| Metrica | Valore | Target |",
            f"|---------|--------|--------|",
            f"| Hit Rate | {quality.get('hit_rate', 0):.1%} | ≥90% |",
        ])
        
        feedback = quality.get('feedback_score', {})
        if isinstance(feedback, dict):
            lines.append(f"| Feedback positivo | {feedback.get('positive_ratio', 0):.1%} | ≥80% |")
        
        lines.append(f"| No-results | {quality.get('no_results_rate', 0):.1%} | ≤10% |")
        
        # Latency
        latency = quality.get('latency_stats', {})
        if latency:
            lines.extend([
                "",
                "### ⏱️ Latenza",
                "",
                f"| Percentile | Valore |",
                f"|------------|--------|",
                f"| Media | {latency.get('avg', 0)}ms |",
                f"| P50 | {latency.get('p50', 0)}ms |",
                f"| P95 | {latency.get('p95', 0)}ms |",
            ])
        
        # Issues
        issues = quality.get('quality_issues', [])
        if issues:
            lines.extend([
                "",
                "### ⚠️ Problemi Rilevati",
                "",
            ])
            for issue in issues:
                severity_icon = "🔴" if issue.get('severity') == 'high' else "🟡"
                lines.append(f"- {severity_icon} {issue.get('description', '')}")
        
        lines.extend([
            "",
            "---",
            "",
            "## 📚 Glossario",
            "",
            f"| Metrica | Valore |",
            f"|---------|--------|",
            f"| Termini totali | {glossary.get('total_terms', 0)} |",
            f"| Termini usati oggi | {glossary.get('terms_used_today', 0)} |",
            f"| Copertura | {glossary.get('coverage_ratio', 0):.1%} |",
            f"| Termini sconosciuti | {glossary.get('unknown_count', 0)} |",
        ])
        
        # Top unknown
        unknown = glossary.get('unknown_terms', [])
        if unknown:
            lines.extend([
                "",
                "**Top termini non riconosciuti:**",
            ])
            for item in unknown[:5]:
                lines.append(f"- `{item.get('term', '')}` ({item.get('count', 0)} volte)")
        
        lines.extend([
            "",
            "---",
            "",
            "## ⚙️ Pipeline",
            "",
            f"| Metrica | Valore |",
            f"|---------|--------|",
            f"| Status collezione | {pipeline.get('collection_status', 'unknown')} |",
            f"| Chunks totali | {pipeline.get('total_chunks', 0)} |",
            f"| VRAM | {pipeline.get('vram_usage_mb', 0)}MB / {pipeline.get('vram_total_mb', 0)}MB |",
        ])
        
        lines.extend([
            "",
            "---",
            "",
            f"*Report generato: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        ])
        
        return "\n".join(lines)
    
    def generate_summary_markdown(self, data: Dict[str, Any]) -> str:
        """
        Genera summary breve per notifiche.
        
        Args:
            data: Dict con metriche principali
            
        Returns:
            String Markdown breve
        """
        date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
        usage = data.get('usage', {})
        quality = data.get('quality', {})
        
        health = quality.get('overall_health', {})
        score = health.get('score', 0)
        
        lines = [
            f"📊 **Report {date}**",
            "",
            f"• Query: {usage.get('total_queries', 0)} | Utenti: {usage.get('unique_users', 0)}",
            f"• Health: {score}/100 | Hit Rate: {quality.get('hit_rate', 0):.1%}",
        ]
        
        issues = quality.get('quality_issues', [])
        if issues:
            high_issues = [i for i in issues if i.get('severity') == 'high']
            if high_issues:
                lines.append(f"• ⚠️ {len(high_issues)} problemi critici")
        
        return "\n".join(lines)
    
    # ═══════════════════════════════════════════════════════════════
    # HTML REPORTS
    # ═══════════════════════════════════════════════════════════════
    
    def generate_daily_html(self, data: Dict[str, Any]) -> str:
        """
        Genera report HTML.
        
        Args:
            data: Dict con tutte le metriche
            
        Returns:
            String HTML
        """
        date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
        usage = data.get('usage', {})
        quality = data.get('quality', {})
        glossary = data.get('glossary', {})
        pipeline = data.get('pipeline', {})
        
        health = quality.get('overall_health', {})
        health_color = health.get('color', 'gray')
        health_score = health.get('score', 0)
        
        html = f"""<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OVV ISO Chat - Report {date}</title>
    <style>
        :root {{
            --primary: #2563eb;
            --success: #22c55e;
            --warning: #eab308;
            --danger: #ef4444;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text: #1e293b;
            --text-muted: #64748b;
        }}
        
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        
        body {{
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
            padding: 2rem;
        }}
        
        .container {{ max-width: 1200px; margin: 0 auto; }}
        
        h1 {{
            font-size: 1.75rem;
            margin-bottom: 1.5rem;
            color: var(--primary);
        }}
        
        h2 {{
            font-size: 1.25rem;
            margin: 1.5rem 0 1rem;
            color: var(--text);
        }}
        
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        
        .kpi-card {{
            background: var(--card-bg);
            border-radius: 12px;
            padding: 1.25rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        
        .kpi-card h3 {{
            font-size: 0.875rem;
            color: var(--text-muted);
            margin-bottom: 0.5rem;
        }}
        
        .kpi-card .value {{
            font-size: 1.75rem;
            font-weight: 700;
        }}
        
        .kpi-card .delta {{
            font-size: 0.75rem;
            margin-top: 0.25rem;
        }}
        
        .kpi-card .delta.positive {{ color: var(--success); }}
        .kpi-card .delta.negative {{ color: var(--danger); }}
        
        .health-badge {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 1rem;
            border-radius: 9999px;
            font-weight: 600;
            background: {self._get_health_bg(health_color)};
            color: {self._get_health_text(health_color)};
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 1rem 0;
            background: var(--card-bg);
            border-radius: 8px;
            overflow: hidden;
        }}
        
        th, td {{
            padding: 0.75rem 1rem;
            text-align: left;
            border-bottom: 1px solid #e2e8f0;
        }}
        
        th {{ background: #f1f5f9; font-weight: 600; }}
        
        .issue {{
            padding: 0.75rem 1rem;
            margin: 0.5rem 0;
            border-radius: 8px;
            border-left: 4px solid;
        }}
        
        .issue.high {{
            background: #fef2f2;
            border-color: var(--danger);
        }}
        
        .issue.medium {{
            background: #fefce8;
            border-color: var(--warning);
        }}
        
        .footer {{
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid #e2e8f0;
            color: var(--text-muted);
            font-size: 0.875rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Report Analytics - {date}</h1>
        
        <div class="health-badge">
            Health Score: {health_score}/100
        </div>
        
        <h2>📈 Panoramica</h2>
        <div class="kpi-grid">
            <div class="kpi-card">
                <h3>Query Totali</h3>
                <div class="value">{usage.get('total_queries', 0)}</div>
            </div>
            <div class="kpi-card">
                <h3>Utenti Attivi</h3>
                <div class="value">{usage.get('unique_users', 0)}</div>
            </div>
            <div class="kpi-card">
                <h3>Hit Rate</h3>
                <div class="value">{quality.get('hit_rate', 0):.1%}</div>
            </div>
            <div class="kpi-card">
                <h3>Feedback Positivo</h3>
                <div class="value">{self._get_feedback_ratio(quality):.1%}</div>
            </div>
        </div>
        
        <h2>⏱️ Latenza</h2>
        <table>
            <tr>
                <th>Metrica</th>
                <th>Valore</th>
            </tr>
            {self._generate_latency_rows(quality.get('latency_stats', {}))}
        </table>
        
        {self._generate_issues_section(quality.get('quality_issues', []))}
        
        <h2>📚 Glossario</h2>
        <table>
            <tr><th>Termini totali</th><td>{glossary.get('total_terms', 0)}</td></tr>
            <tr><th>Usati oggi</th><td>{glossary.get('terms_used_today', 0)}</td></tr>
            <tr><th>Copertura</th><td>{glossary.get('coverage_ratio', 0):.1%}</td></tr>
            <tr><th>Non riconosciuti</th><td>{glossary.get('unknown_count', 0)}</td></tr>
        </table>
        
        <h2>⚙️ Pipeline</h2>
        <table>
            <tr><th>Status</th><td>{pipeline.get('collection_status', 'unknown')}</td></tr>
            <tr><th>Chunks</th><td>{pipeline.get('total_chunks', 0)}</td></tr>
            <tr><th>VRAM</th><td>{pipeline.get('vram_usage_mb', 0)}MB / {pipeline.get('vram_total_mb', 0)}MB</td></tr>
        </table>
        
        <div class="footer">
            Report generato: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        </div>
    </div>
</body>
</html>"""
        
        return html
    
    def _get_health_bg(self, color: str) -> str:
        """Background color per health badge"""
        colors = {
            'green': '#dcfce7',
            'lime': '#ecfccb',
            'yellow': '#fef9c3',
            'orange': '#ffedd5',
            'red': '#fee2e2',
            'gray': '#f1f5f9'
        }
        return colors.get(color, colors['gray'])
    
    def _get_health_text(self, color: str) -> str:
        """Text color per health badge"""
        colors = {
            'green': '#166534',
            'lime': '#3f6212',
            'yellow': '#854d0e',
            'orange': '#9a3412',
            'red': '#991b1b',
            'gray': '#475569'
        }
        return colors.get(color, colors['gray'])
    
    def _get_feedback_ratio(self, quality: Dict) -> float:
        """Estrae feedback ratio"""
        feedback = quality.get('feedback_score', {})
        if isinstance(feedback, dict):
            return feedback.get('positive_ratio', 0)
        return 0
    
    def _generate_latency_rows(self, latency: Dict) -> str:
        """Genera righe tabella latenza"""
        rows = []
        if latency:
            rows.append(f"<tr><td>Media</td><td>{latency.get('avg', 0)}ms</td></tr>")
            rows.append(f"<tr><td>P50</td><td>{latency.get('p50', 0)}ms</td></tr>")
            rows.append(f"<tr><td>P95</td><td>{latency.get('p95', 0)}ms</td></tr>")
            rows.append(f"<tr><td>P99</td><td>{latency.get('p99', 0)}ms</td></tr>")
        return "\n".join(rows)
    
    def _generate_issues_section(self, issues: List[Dict]) -> str:
        """Genera sezione issues"""
        if not issues:
            return ""
        
        html = "<h2>⚠️ Problemi</h2>\n"
        for issue in issues:
            severity = issue.get('severity', 'medium')
            desc = issue.get('description', '')
            html += f'<div class="issue {severity}">{desc}</div>\n'
        
        return html
    
    # ═══════════════════════════════════════════════════════════════
    # FILE OPERATIONS
    # ═══════════════════════════════════════════════════════════════
    
    def save_report(
        self,
        content: str,
        filename: str,
        format: str = "md"
    ) -> Path:
        """
        Salva report su file.
        
        Args:
            content: Contenuto report
            filename: Nome file (senza estensione)
            format: "md" o "html"
            
        Returns:
            Path del file salvato
        """
        ext = "html" if format == "html" else "md"
        filepath = self.output_dir / f"{filename}.{ext}"
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        
        logger.info(f"Report salvato: {filepath}")
        return filepath
    
    def list_reports(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Lista report salvati.
        
        Returns:
            Lista {name, path, date, format}
        """
        reports = []
        
        for filepath in sorted(self.output_dir.glob("*.*"), reverse=True):
            if filepath.suffix in ['.md', '.html']:
                reports.append({
                    "name": filepath.stem,
                    "path": str(filepath),
                    "format": filepath.suffix[1:],
                    "modified": datetime.fromtimestamp(filepath.stat().st_mtime).isoformat()
                })
        
        return reports[:limit]


# Test standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    import tempfile
    import shutil
    
    print("=== TEST REPORT GENERATOR ===\n")
    
    temp_dir = tempfile.mkdtemp()
    generator = ReportGenerator(output_dir=temp_dir)
    
    # Dati di test
    test_data = {
        "date": "2025-12-08",
        "usage": {
            "total_queries": 147,
            "unique_users": 23,
            "trend": {"pct_change": 12.5}
        },
        "quality": {
            "hit_rate": 0.89,
            "feedback_score": {"positive_ratio": 0.82, "total_with_feedback": 45},
            "no_results_rate": 0.08,
            "latency_stats": {"avg": 2847, "p50": 2500, "p95": 5000, "p99": 8000},
            "quality_issues": [
                {"severity": "medium", "description": "Hit rate 89% sotto target 90%"}
            ],
            "overall_health": {"score": 78, "status": "good", "color": "lime"}
        },
        "glossary": {
            "total_terms": 211,
            "terms_used_today": 45,
            "coverage_ratio": 0.65,
            "unknown_count": 12,
            "unknown_terms": [
                {"term": "XYZ", "count": 5},
                {"term": "ABC", "count": 3}
            ]
        },
        "pipeline": {
            "collection_status": "green",
            "total_chunks": 4521,
            "vram_usage_mb": 5100,
            "vram_total_mb": 6144
        }
    }
    
    # Test 1: Markdown report
    print("Test 1: Generate Markdown")
    md_report = generator.generate_daily_markdown(test_data)
    print(md_report[:500])
    print("...\n")
    
    # Test 2: Summary
    print("Test 2: Generate Summary")
    summary = generator.generate_summary_markdown(test_data)
    print(summary)
    print()
    
    # Test 3: HTML report
    print("Test 3: Generate HTML")
    html_report = generator.generate_daily_html(test_data)
    print(f"  HTML length: {len(html_report)} chars")
    print()
    
    # Test 4: Save reports
    print("Test 4: Save reports")
    md_path = generator.save_report(md_report, "daily_2025-12-08", "md")
    html_path = generator.save_report(html_report, "daily_2025-12-08", "html")
    print(f"  Saved: {md_path}")
    print(f"  Saved: {html_path}")
    print()
    
    # Test 5: List reports
    print("Test 5: List reports")
    reports = generator.list_reports()
    for r in reports:
        print(f"  - {r['name']}.{r['format']}")
    
    # Cleanup
    shutil.rmtree(temp_dir)
    
    print("\n✅ Test completati!")

