# ECharts Reference

Use `https://cdn.jsdelivr.net/npm/echarts@6.1.0/dist/echarts.min.js`. Check `window.echarts` before initialization and show an in-page error if loading fails.

- Time trend: line
- Category comparison: bar, horizontal for long labels
- Correlation/outliers: scatter
- Distribution: boxplot or histogram
- Hierarchy: tree, treemap, or sunburst
- Flow: sankey or funnel

Include tooltip and a legend for multi-series data. Add data zoom only for crowded data. Do not enable `saveAsImage` unless requested.
