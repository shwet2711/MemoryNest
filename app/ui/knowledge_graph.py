
from __future__ import annotations

import html

import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network

from app.services.knowledge_graph_service import (
    get_user_knowledge_graph,
)


def _build_interactive_graph(
    relationships: list[dict],
    focus_entity: str = "",
) -> tuple[str, int]:
    """Build an interactive graph from all returned relationships."""

    network = Network(
        height="680px",
        width="100%",
        directed=True,
        bgcolor="#0B1220",
        font_color="#E5E7EB",
        cdn_resources="in_line",
    )

    network.set_options(
        """
        {
          "nodes": {
            "shape": "dot",
            "size": 23,
            "borderWidth": 2,
            "font": {
              "size": 15,
              "face": "Arial",
              "color": "#F1F5F9",
              "strokeWidth": 3,
              "strokeColor": "#0B1220"
            },
            "shadow": true
          },
          "edges": {
            "arrows": {
              "to": {
                "enabled": true,
                "scaleFactor": 0.7
              }
            },
            "color": {
              "color": "#64748B",
              "highlight": "#38BDF8",
              "hover": "#38BDF8"
            },
            "font": {
              "size": 11,
              "color": "#CBD5E1",
              "face": "Arial",
              "strokeWidth": 3,
              "strokeColor": "#0B1220",
              "align": "middle"
            },
            "smooth": {
              "enabled": true,
              "type": "dynamic"
            },
            "width": 1.8
          },
          "physics": {
            "enabled": true,
            "stabilization": {
              "enabled": true,
              "iterations": 200,
              "fit": true
            },
            "barnesHut": {
              "gravitationalConstant": -3500,
              "centralGravity": 0.25,
              "springLength": 155,
              "springConstant": 0.035,
              "damping": 0.18,
              "avoidOverlap": 0.7
            }
          },
          "interaction": {
            "hover": true,
            "navigationButtons": true,
            "keyboard": {
              "enabled": true
            },
            "zoomView": true,
            "dragView": true,
            "dragNodes": true,
            "multiselect": true
          }
        }
        """
    )

    entity_ids: dict[str, str] = {}
    focus_key = focus_entity.casefold().strip()

    def add_entity(
        name: str,
        entity_type: str | None,
    ) -> str:
        clean_name = name.strip() or "Unknown entity"
        key = clean_name.casefold()

        if key in entity_ids:
            return entity_ids[key]

        node_id = f"entity_{len(entity_ids)}"
        entity_ids[key] = node_id

        is_focus = bool(focus_key and key == focus_key)

        colors = (
            {
                "background": "#F59E0B",
                "border": "#FDE68A",
                "highlight": {
                    "background": "#FBBF24",
                    "border": "#FFFFFF"
                }
            }
            if is_focus
            else {
                "background": "#2563EB",
                "border": "#60A5FA",
                "highlight": {
                    "background": "#0EA5E9",
                    "border": "#BAE6FD"
                }
            }
        )

        safe_name = html.escape(clean_name)
        safe_type = html.escape(str(entity_type or "Unknown"))

        network.add_node(
            node_id,
            label=clean_name,
            title=f"<b>{safe_name}</b><br>Type: {safe_type}",
            color=colors,
            size=32 if is_focus else 23,
            borderWidth=3 if is_focus else 2,
        )

        return node_id

    seen_edges: set[tuple] = set()

    for item in relationships:
        subject = str(
            item.get("subject") or "Unknown entity"
        ).strip()

        related = str(
            item.get("object") or "Unknown entity"
        ).strip()

        relation = str(
            item.get("relationship") or "RELATED_TO"
        ).strip()

        document_id = item.get("document_id")
        chunk_index = item.get("chunk_index")

        edge_key = (
            subject.casefold(),
            relation.casefold(),
            related.casefold(),
            document_id,
            chunk_index,
        )

        if edge_key in seen_edges:
            continue

        seen_edges.add(edge_key)

        source_id = add_entity(
            subject,
            item.get("subject_type"),
        )
        target_id = add_entity(
            related,
            item.get("object_type"),
        )

        source = html.escape(
            str(item.get("source_filename") or "Unknown")
        )
        safe_relation = html.escape(relation)

        network.add_edge(
            source_id,
            target_id,
            label=relation,
            title=(
                f"<b>{safe_relation}</b>"
                f"<br>Source: {source}"
                f"<br>Document ID: {document_id or 'N/A'}"
                f"<br>Chunk index: "
                f"{chunk_index if chunk_index is not None else 'N/A'}"
            ),
        )

    return network.generate_html(), len(entity_ids)


def knowledge_graph_page() -> None:
    """Display the complete knowledge graph for the signed-in user."""

    st.title("Knowledge Graph")
    st.caption(
        "Explore connections across your documents "
        "using the complete graph stored in Neo4j."
    )

    user_id = st.session_state.get("user_id")

    if user_id is None:
        st.warning("Please sign in to access your knowledge graph.")
        return

    # --------------------------------------------------------
    # LOAD COMPLETE GRAPH
    # --------------------------------------------------------

    cached_user = st.session_state.get(
        "knowledge_graph_loaded_user"
    )

    refresh_requested = st.session_state.pop(
        "knowledge_graph_refresh_requested",
        False,
    )

    if (
        cached_user != int(user_id)
        or "knowledge_graph_all_relationships" not in st.session_state
        or refresh_requested
    ):
        try:
            with st.spinner("Loading your complete knowledge graph..."):
                all_relationships = get_user_knowledge_graph(
                    user_id=int(user_id)
                )

            st.session_state[
                "knowledge_graph_all_relationships"
            ] = all_relationships

            st.session_state[
                "knowledge_graph_loaded_user"
            ] = int(user_id)

            st.session_state[
                "knowledge_graph_load_error"
            ] = None

        except Exception:
            st.session_state[
                "knowledge_graph_load_error"
            ] = (
                "Could not load your knowledge graph. "
                "Check that Neo4j is running and enabled."
            )

    load_error = st.session_state.get(
        "knowledge_graph_load_error"
    )

    if load_error:
        st.error(load_error)
        return

    relationships = st.session_state.get(
        "knowledge_graph_all_relationships",
        [],
    )

    # --------------------------------------------------------
    # SEARCH / FOCUS AND REFRESH
    # --------------------------------------------------------

    search_col, refresh_col = st.columns([4, 1])

    with search_col:
        with st.form("knowledge_graph_focus_form"):
            focus_entity = st.text_input(
                "Find an entity in the complete graph",
                value=st.session_state.get(
                    "knowledge_graph_focus_entity", ""
                ),
                placeholder="For example: MemoryNest or SQLite",
                max_chars=200,
            )

            submitted = st.form_submit_button(
                "Highlight entity",
                width="stretch",
            )

    if submitted:
        st.session_state[
            "knowledge_graph_focus_entity"
        ] = focus_entity.strip()

    with refresh_col:
        st.write("")
        st.write("")
        if st.button("Refresh graph", width="stretch"):
            st.session_state[
                "knowledge_graph_refresh_requested"
            ] = True
            st.rerun()

    focus_entity = st.session_state.get(
        "knowledge_graph_focus_entity",
        "",
    )

    if not relationships:
        st.info(
            "No relationships are stored in your graph yet. "
            "Upload and process documents that contain "
            "extractable entity relationships."
        )
        return

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    entity_names: set[str] = set()

    for item in relationships:
        entity_names.add(
            str(item.get("subject") or "Unknown entity").casefold()
        )
        entity_names.add(
            str(item.get("object") or "Unknown entity").casefold()
        )

    metric_col1, metric_col2 = st.columns(2)

    metric_col1.metric(
        "Stored relationships",
        len(relationships),
    )

    metric_col2.metric(
        "Connected entities",
        len(entity_names),
    )

    st.divider()

    # --------------------------------------------------------
    # VIEW SELECTOR
    # --------------------------------------------------------

    view_mode = st.radio(
        "Choose how to view your complete graph",
        options=["Both", "Graph", "Table"],
        horizontal=True,
        key="knowledge_graph_view_mode",
    )

    # --------------------------------------------------------
    # INTERACTIVE GRAPH
    # --------------------------------------------------------

    if view_mode in ("Both", "Graph"):
        st.subheader("Interactive knowledge map")

        st.caption(
            "This graph uses all relationships loaded for your account. "
            "Drag nodes, zoom with your mouse wheel, move the canvas, "
            "and hover over connections to inspect source information. "
            "An exact matching search result is highlighted in amber."
        )

        try:
            graph_html, graph_entity_count = _build_interactive_graph(
                relationships,
                focus_entity,
            )

            st.caption(
                f"Visualizing {graph_entity_count} entities "
                f"and {len(relationships)} stored relationships."
            )

            components.html(
                graph_html,
                height=700,
                scrolling=False,
            )

            if focus_entity and not any(
                focus_entity.casefold()
                == str(name).casefold()
                for item in relationships
                for name in (
                    item.get("subject", ""),
                    item.get("object", ""),
                )
            ):
                st.warning(
                    f"'{focus_entity}' was not found in the loaded graph. "
                    "The complete graph is still displayed."
                )

        except Exception:
            st.error(
                "The interactive graph could not be rendered. "
                "Check the application logs for details."
            )

    # --------------------------------------------------------
    # COMPLETE RELATIONSHIP TABLE
    # --------------------------------------------------------

    if view_mode in ("Both", "Table"):
        st.subheader("All stored relationships")

        table_rows = [
            {
                "Subject": item.get("subject") or "",
                "Subject type": item.get("subject_type") or "",
                "Relationship": item.get("relationship") or "",
                "Related entity": item.get("object") or "",
                "Related entity type": item.get("object_type") or "",
                "Source document": item.get("source_filename") or "",
                "Document ID": item.get("document_id"),
                "Chunk index": item.get("chunk_index"),
            }
            for item in relationships
        ]

        st.dataframe(
            table_rows,
            width="stretch",
            hide_index=True,
        )

    # --------------------------------------------------------
    # SOURCE DETAILS
    # --------------------------------------------------------

    if view_mode in ("Both", "Table"):
        st.subheader("Relationship source details")

        for index, item in enumerate(relationships, start=1):
            subject = item.get("subject") or "Unknown entity"
            relation = item.get("relationship") or "RELATED_TO"
            related = item.get("object") or "Unknown entity"

            with st.expander(
                f"{index}. {subject} — {relation} — {related}"
            ):
                left, right = st.columns(2)

                with left:
                    st.markdown("**Subject**")
                    st.write(subject)
                    st.caption(
                        f"Type: {item.get('subject_type') or 'Unknown'}"
                    )

                with right:
                    st.markdown("**Related entity**")
                    st.write(related)
                    st.caption(
                        f"Type: {item.get('object_type') or 'Unknown'}"
                    )

                st.markdown("**Relationship**")
                st.write(relation)

                st.markdown("**Source document**")
                st.write(
                    item.get("source_filename") or "Not available"
                )

                left, right = st.columns(2)

                with left:
                    st.markdown("**Document ID**")
                    st.write(
                        item.get("document_id")
                        if item.get("document_id") is not None
                        else "Not available"
                    )

                with right:
                    st.markdown("**Chunk index**")
                    st.write(
                        item.get("chunk_index")
                        if item.get("chunk_index") is not None
                        else "Not available"
                    )
