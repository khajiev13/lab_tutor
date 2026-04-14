"""
Visualize LangGraph workflow structure using built-in LangGraph methods.

This script generates diagrams directly from the compiled LangGraph workflow.
"""

from pathlib import Path
from services.enhanced_langgraph_service import EnhancedRelationshipService
from neo4j_database import Neo4jService
from models.langgraph_state_models import WorkflowConfiguration
import os
from dotenv import load_dotenv

load_dotenv()


def visualize_workflow():
    """Generate and save workflow visualizations."""
    
    print("🎨 LangGraph Workflow Visualization")
    print("=" * 80)
    
    # Initialize service (we just need the workflow, not to run it)
    neo4j_service = Neo4jService(
        url=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        username=os.getenv("NEO4J_USERNAME", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD", "password")
    )
    
    config = WorkflowConfiguration(
        max_iterations=5,
        verbose_logging=False,
        relationship_types={
            "HAS_COMPONENT": "Has component or part",
            "USES": "Uses or applies",
            "ENABLES": "Enables or facilitates",
            "EXAMPLE_OF": "Is an example of"
        }
    )
    
    service = EnhancedRelationshipService(
        neo4j_service=neo4j_service,
        config=config
    )
    
    # Get the compiled workflow
    workflow = service.workflow
    
    # Create diagrams directory
    diagrams_dir = Path("diagrams")
    diagrams_dir.mkdir(exist_ok=True)
    
    # === 1. MERMAID DIAGRAM (Text) ===
    print("\n📊 Generating Mermaid diagram...")
    try:
        # Get the graph structure
        graph = workflow.get_graph()
        
        # Generate Mermaid diagram
        mermaid_diagram = graph.draw_mermaid()
        
        # Save to file
        mermaid_path = diagrams_dir / "langgraph_workflow.mmd"
        with open(mermaid_path, 'w', encoding='utf-8') as f:
            f.write(mermaid_diagram)
        
        print(f"✅ Mermaid diagram saved to: {mermaid_path}")
        print(f"   View at: https://mermaid.live/")
        
        # Print the diagram
        print("\n" + "=" * 80)
        print("MERMAID DIAGRAM:")
        print("=" * 80)
        print(mermaid_diagram)
        print("=" * 80)
        
    except Exception as e:
        print(f"❌ Error generating Mermaid diagram: {e}")
    
    # === 2. PNG DIAGRAM (Visual) ===
    print("\n🖼️  Generating PNG diagram...")
    try:
        # Generate PNG (requires graphviz or similar)
        png_data = graph.draw_mermaid_png()
        
        # Save to file
        png_path = diagrams_dir / "langgraph_workflow.png"
        with open(png_path, 'wb') as f:
            f.write(png_data)
        
        print(f"✅ PNG diagram saved to: {png_path}")
        
    except ImportError as e:
        print(f"⚠️  Missing dependency for PNG generation: {e}")
        print("   You can still use the Mermaid diagram (.mmd file)")
        print("   View it at: https://mermaid.live/")
    except Exception as e:
        print(f"ℹ️  PNG generation not available: {e}")
        print("   This is optional - the Mermaid diagram (.mmd file) is enough")
        print("   View it at: https://mermaid.live/")
    
    # === 3. ASCII REPRESENTATION ===
    print("\n📝 Graph Structure (ASCII):")
    print("=" * 80)
    try:
        # Get graph info
        nodes = graph.nodes
        edges = graph.edges
        
        print(f"Nodes ({len(nodes)}):")
        for node_id in nodes:
            print(f"  - {node_id}")
        
        print(f"\nEdges ({len(edges)}):")
        for edge in edges:
            start = edge.source
            end = edge.target
            print(f"  {start} → {end}")
        
        print("=" * 80)
        
    except Exception as e:
        print(f"❌ Error displaying graph structure: {e}")
    
    print(f"\n✅ Visualization complete!")
    print(f"📁 Check the {diagrams_dir}/ directory for output files")
    
    # Cleanup
    neo4j_service.close()


if __name__ == "__main__":
    visualize_workflow()

