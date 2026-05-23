# -*- coding: utf-8 -*-

def ui_extra_style():
    return """
<style>
body { font-size: 13px; }
.ui-note { padding: 10px 12px; border-radius: 10px; background: #111827; color: #e5e7eb; margin: 8px 0 14px 0; }
.top-card { margin: 14px 0 22px 0; padding: 12px; border-radius: 12px; overflow-x: auto; }
.top-green { background: #062f22; border: 1px solid #16a34a; }
.top-red { background: #3a0b0b; border: 1px solid #dc2626; }
.top-card h3 { margin-top: 0; color: #ffffff; }
.top-card table { width: 100%; border-collapse: collapse; font-size: 12px; }
.top-card th { position: sticky; top: 0; background: #111827; color: #ffffff; }
.top-card td, .top-card th { padding: 7px 8px; border: 1px solid rgba(255,255,255,0.14); white-space: nowrap; }
.top-card td { color: #f9fafb; font-weight: 600; }
.top-card td:first-child {
  font-size: 15px;
  font-weight: 900;
  letter-spacing: 0.7px;
  text-align: center;
  min-width: 54px;
  border-radius: 8px;
  position: sticky;
  left: 0;
  z-index: 2;
}
.top-card th:first-child {
  position: sticky;
  left: 0;
  z-index: 3;
}
.top-green td:first-child {
  color: #ffffff;
  background: linear-gradient(135deg, #16a34a, #065f46);
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.35), 0 0 8px rgba(34,197,94,0.35);
}
.top-red td:first-child {
  color: #ffffff;
  background: linear-gradient(135deg, #dc2626, #7f1d1d);
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.28), 0 0 8px rgba(239,68,68,0.35);
}
.full-note { color: #d1d5db; font-size: 12px; margin-top: -6px; }

.v134-scroll { overflow-x: auto; width: 100%; }
.v134-full-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.v134-full-table th { position: sticky; top: 0; background: #111827; color: #ffffff; z-index: 1; }
.v134-full-table td, .v134-full-table th { padding: 8px 8px; border: 1px solid rgba(255,255,255,0.13); vertical-align: middle; }
.v134-full-table td { color: #f3f4f6; font-weight: 600; }
.v134-row-green { background: #063b2a !important; }
.v134-row-red { background: #401010 !important; }
.v134-row-neutral { background: #151923 !important; }
.v134-symbol-cell { position: sticky; left: 0; z-index: 2; background: inherit !important; text-align: center; min-width: 68px; }
.v134-full-table th:first-child { position: sticky; left: 0; z-index: 3; }
.v134-symbol-badge { display: inline-block; min-width: 48px; padding: 7px 10px; border-radius: 9px; font-size: 15px; font-weight: 900; letter-spacing: 0.8px; color: #ffffff; }
.v134-symbol-green { background: linear-gradient(135deg, #22c55e, #047857); box-shadow: 0 0 10px rgba(34,197,94,0.55), inset 0 0 0 1px rgba(255,255,255,0.35); }
.v134-symbol-red { background: linear-gradient(135deg, #ef4444, #7f1d1d); box-shadow: 0 0 10px rgba(239,68,68,0.55), inset 0 0 0 1px rgba(255,255,255,0.28); }
.v134-symbol-neutral { background: linear-gradient(135deg, #64748b, #334155); box-shadow: 0 0 8px rgba(148,163,184,0.35), inset 0 0 0 1px rgba(255,255,255,0.22); }
</style>
"""
