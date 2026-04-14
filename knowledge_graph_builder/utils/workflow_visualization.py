"""
Workflow Visualization Utilities

This module provides tools to visualize the LangGraph workflow structure,
state transitions, and quality metrics progression.
"""

import json
from typing import Dict, List, Optional
from pathlib import Path


def generate_workflow_mermaid() -> str:
    """
    Generate Mermaid diagram for the enhanced LangGraph workflow.
    
    Returns:
        Mermaid diagram as string
    """
    return """
graph TD
    START([START]) --> INIT[Initialize State]
    INIT --> GEN{Generation Node}
    
    GEN -->|First Iteration| GEN1[Generate Initial<br/>Comprehensive Set]
    GEN -->|Later Iterations| GEN2[Apply Operations<br/>from Feedback]
    
    GEN1 --> VAL[Validation Node]
    GEN2 --> VAL
    
    VAL --> CALC[Calculate Quality Scores<br/>Accuracy, Relevance, Completeness]
    CALC --> OPS[Identify Operations<br/>Modify, Delete, Add]
    OPS --> HIST[Update State History<br/>& Convergence Metrics]
    
    HIST --> CONV{Convergence<br/>Checker}
    
    CONV -->|Quality ≥ 0.85| END1([COMPLETE])
    CONV -->|No Operations| END2([COMPLETE])
    CONV -->|Max Iterations| END3([COMPLETE])
    CONV -->|Diminishing Returns| END4([COMPLETE])
    CONV -->|Continue| GEN
    
    style START fill:#90EE90
    style END1 fill:#FFB6C1
    style END2 fill:#FFB6C1
    style END3 fill:#FFB6C1
    style END4 fill:#FFB6C1
    style GEN fill:#87CEEB
    style VAL fill:#DDA0DD
    style CONV fill:#F0E68C
"""


def generate_quality_trend_chart(workflow_stats: Dict) -> str:
    """
    Generate ASCII chart for quality trend across iterations.
    
    Args:
        workflow_stats: Workflow statistics dictionary
        
    Returns:
        ASCII chart as string
    """
    convergence = workflow_stats.get("convergence", {})
    quality_trend = convergence.get("quality_trend", [])
    
    if not quality_trend:
        return "No quality trend data available"
    
    # Create ASCII chart
    chart_lines = []
    chart_lines.append("\n📈 Quality Score Progression")
    chart_lines.append("=" * 60)
    
    max_score = 1.0
    chart_width = 50
    
    for i, score in enumerate(quality_trend):
        bar_length = int(score * chart_width)
        bar = "█" * bar_length
        chart_lines.append(f"Iter {i+1}: {bar} {score:.3f}")
    
    chart_lines.append("=" * 60)
    chart_lines.append(f"Target: {'█' * int(0.85 * chart_width)} 0.850")
    
    return "\n".join(chart_lines)


def generate_operations_trend_chart(workflow_stats: Dict) -> str:
    """
    Generate ASCII chart for operations trend across iterations.
    
    Args:
        workflow_stats: Workflow statistics dictionary
        
    Returns:
        ASCII chart as string
    """
    convergence = workflow_stats.get("convergence", {})
    operations_trend = convergence.get("operations_trend", [])
    
    if not operations_trend:
        return "No operations trend data available"
    
    # Create ASCII chart
    chart_lines = []
    chart_lines.append("\n🔧 Operations Count Progression")
    chart_lines.append("=" * 60)
    
    max_ops = max(operations_trend) if operations_trend else 1
    chart_width = 50
    
    for i, ops in enumerate(operations_trend):
        if max_ops > 0:
            bar_length = int((ops / max_ops) * chart_width)
        else:
            bar_length = 0
        bar = "▓" * bar_length
        chart_lines.append(f"Iter {i+1}: {bar} {ops} ops")
    
    chart_lines.append("=" * 60)
    chart_lines.append("Target: 0 operations (convergence)")
    
    return "\n".join(chart_lines)


def generate_iteration_summary_table(workflow_stats: Dict, iteration_history: Optional[List[Dict]] = None) -> str:
    """
    Generate ASCII table summarizing all iterations.
    
    Args:
        workflow_stats: Workflow statistics dictionary
        iteration_history: Optional iteration history from output file
        
    Returns:
        ASCII table as string
    """
    convergence = workflow_stats.get("convergence", {})
    quality_trend = convergence.get("quality_trend", [])
    operations_trend = convergence.get("operations_trend", [])
    rel_count_trend = convergence.get("relationship_count_trend", [])
    
    if not quality_trend:
        return "No iteration data available"
    
    # Create table
    table_lines = []
    table_lines.append("\n📊 Iteration Summary")
    table_lines.append("=" * 80)
    table_lines.append(f"{'Iter':<6} {'Rels':<8} {'Quality':<10} {'Ops':<8} {'Status':<30}")
    table_lines.append("-" * 80)
    
    for i in range(len(quality_trend)):
        iter_num = i + 1
        rel_count = rel_count_trend[i] if i < len(rel_count_trend) else "N/A"
        quality = quality_trend[i]
        ops = operations_trend[i] if i < len(operations_trend) else "N/A"
        
        # Determine status
        if quality >= 0.85:
            status = "✅ Quality threshold met"
        elif ops == 0:
            status = "✅ No operations needed"
        elif i == len(quality_trend) - 1:
            status = "🏁 Final iteration"
        else:
            status = "🔄 Refining..."
        
        table_lines.append(f"{iter_num:<6} {rel_count:<8} {quality:<10.3f} {ops:<8} {status:<30}")
    
    table_lines.append("=" * 80)
    
    return "\n".join(table_lines)


def visualize_workflow_results(output_file: str):
    """
    Load workflow results and generate comprehensive visualizations.
    
    Args:
        output_file: Path to the output JSON file
    """
    # Load results
    output_path = Path(output_file)
    if not output_path.exists():
        print(f"❌ Output file not found: {output_file}")
        return
    
    with open(output_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    metadata = data.get("metadata", {})
    iteration_history = data.get("iteration_history", [])
    
    # Print header
    print("\n" + "=" * 80)
    print("🎨 WORKFLOW VISUALIZATION")
    print("=" * 80)
    
    # Print workflow diagram
    print("\n📊 Workflow Structure:")
    print(generate_workflow_mermaid())
    
    # Print quality trend
    print(generate_quality_trend_chart(metadata))
    
    # Print operations trend
    print(generate_operations_trend_chart(metadata))
    
    # Print iteration summary
    print(generate_iteration_summary_table(metadata, iteration_history))
    
    # Print convergence summary
    convergence = metadata.get("convergence", {})
    print("\n🎯 Convergence Summary")
    print("=" * 80)
    print(f"Status: {'✅ Achieved' if convergence.get('achieved') else '❌ Not Achieved'}")
    print(f"Reason: {convergence.get('reason', 'N/A')}")
    print(f"Final Quality: {convergence.get('final_quality_score', 0):.3f}")
    print(f"Total Iterations: {metadata.get('total_iterations', 0)}")
    print(f"Processing Time: {metadata.get('processing_time_seconds', 0):.2f}s")
    print("=" * 80)


def generate_state_transition_diagram(iteration_history: List[Dict]) -> str:
    """
    Generate Mermaid state transition diagram from iteration history.
    
    Args:
        iteration_history: List of iteration snapshots
        
    Returns:
        Mermaid diagram as string
    """
    if not iteration_history:
        return "No iteration history available"
    
    diagram_lines = ["stateDiagram-v2"]
    diagram_lines.append("    [*] --> Iteration0")
    
    for i, snapshot in enumerate(iteration_history):
        iter_num = snapshot.get("iteration", i)
        rel_count = snapshot.get("relationship_count", 0)
        quality = snapshot.get("quality_metrics", {})
        overall_score = quality.get("overall_score", 0) if quality else 0
        ops = snapshot.get("operations_applied", 0)
        
        state_name = f"Iteration{iter_num}"
        state_label = f"Iteration {iter_num + 1}\\nRels: {rel_count}\\nQuality: {overall_score:.2f}\\nOps: {ops}"
        
        diagram_lines.append(f"    {state_name}: {state_label}")
        
        if i < len(iteration_history) - 1:
            next_state = f"Iteration{iter_num + 1}"
            diagram_lines.append(f"    {state_name} --> {next_state}")
        else:
            diagram_lines.append(f"    {state_name} --> [*]")
    
    return "\n".join(diagram_lines)


def print_relationship_type_distribution(relationships: List[Dict]):
    """
    Print distribution of relationship types with ASCII bar chart.
    
    Args:
        relationships: List of relationship dictionaries
    """
    if not relationships:
        print("No relationships to analyze")
        return
    
    # Count relationship types
    type_counts = {}
    for rel in relationships:
        rel_type = rel.get("relation", "UNKNOWN")
        type_counts[rel_type] = type_counts.get(rel_type, 0) + 1
    
    # Print distribution
    print("\n📊 Relationship Type Distribution")
    print("=" * 80)
    
    total = len(relationships)
    max_count = max(type_counts.values())
    chart_width = 50
    
    for rel_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total) * 100
        bar_length = int((count / max_count) * chart_width)
        bar = "█" * bar_length
        
        print(f"{rel_type:<15} {bar} {count:>4} ({percentage:>5.1f}%)")
    
    print("=" * 80)
    print(f"Total: {total} relationships")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python workflow_visualization.py <output_file.json>")
        sys.exit(1)
    
    output_file = sys.argv[1]
    visualize_workflow_results(output_file)

