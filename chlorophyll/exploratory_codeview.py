from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from tkinter import Menu, Misc, ttk, messagebox
from typing import Any, Callable, Dict, List, Optional, Tuple

from .codeview import CodeView, LexerType


@dataclass
class Variant:
    """Represents a code variant with its content and metadata."""
    id: str
    content: str
    name: str
    start_line: int
    end_line: int
    start_col: int
    end_col: int
    created_at: float = field(default_factory=lambda: __import__('time').time())


@dataclass
class VariantGroup:
    """Represents a group of variants for the same code section."""
    id: str
    original_content: str
    start_line: int
    end_line: int
    start_col: int
    end_col: int
    variants: List[Variant] = field(default_factory=list)
    active_variant_id: Optional[str] = None


class InPlaceSplitView(ttk.Frame):
    """An in-place split view for displaying variants within the main editor."""
    
    def __init__(self, master: Misc, variant_group: VariantGroup, parent_codeview: 'ExploratoryCodeView', **kwargs):
        super().__init__(master, **kwargs)
        self.variant_group = variant_group
        self.parent_codeview = parent_codeview
        self.variant_text_widgets: Dict[str, Dict[str, Any]] = {}
        
        # Create header with controls - make it more compact
        self.header_frame = ttk.Frame(self)
        self.header_frame.pack(fill="x", pady=0)
        
        # Create split container
        self.split_container = ttk.Frame(self)
        self.split_container.pack(fill="both", expand=True)
        
        # Create paned window for variants
        self.paned_window = ttk.PanedWindow(self.split_container, orient="horizontal")
        self.paned_window.pack(fill="both", expand=True, padx=0, pady=0)
        
        self._create_controls()
        self._create_variant_views()
    
    def _create_controls(self):
        """Create control buttons for variant management."""
        # Left side - controls (full button text when space allows)
        ttk.Button(self.header_frame, text="Add Variant",
                  command=self._add_variant).pack(side="left", padx=(2, 2))
        ttk.Button(self.header_frame, text="Merge",
                  command=self._merge_selected).pack(side="left", padx=(0, 2))
        ttk.Button(self.header_frame, text="Close",
                  command=self._close_split).pack(side="left", padx=(0, 2))
    
    def _create_variant_views(self):
        """Create text widgets for each variant."""
        # Calculate the maximum height needed for all variants
        max_lines = max(variant.content.count('\n') + 1 for variant in self.variant_group.variants)
        max_lines = max(max_lines, 1)  # Minimum height
        
        # Store max height for use in individual variant creation
        self.max_variant_height = max_lines
        
        for variant in self.variant_group.variants:
            self._create_variant_view(variant)
    
    def _create_variant_view(self, variant: Variant):
        """Create a minimal text widget for a single variant."""
        # Create frame for this variant
        variant_frame = ttk.Frame(self.paned_window)
        
        # Create text widget directly - no header, no line numbers
        import tkinter as tk
        text_widget = tk.Text(
            variant_frame,
            wrap="none",
            font=self.parent_codeview.cget("font"),
            bg=self.parent_codeview.cget("bg"),
            fg=self.parent_codeview.cget("fg"),
            insertbackground=self.parent_codeview.cget("insertbackground"),
            selectbackground=self.parent_codeview.cget("selectbackground"),
            selectforeground=self.parent_codeview.cget("selectforeground"),
            height=self.max_variant_height,
            width=40,
            bd=0,
            relief="solid"
        )
        text_widget.pack(fill="both", expand=True)
        
        # Set content
        text_widget.delete("1.0", "end")
        text_widget.insert("1.0", variant.content)
        
        # Apply syntax highlighting
        self._apply_highlighting(text_widget, variant.content)
        
        # Create context menu
        context_menu = tk.Menu(text_widget, tearoff=0)
        context_menu.add_command(label=f"Rename '{variant.name}'", command=lambda: self._rename_variant(variant.id))
        context_menu.add_command(label=f"Delete '{variant.name}'", command=lambda: self._delete_variant(variant.id))
        context_menu.add_separator()
        context_menu.add_command(label="Set as Active", command=lambda: self._set_active_variant(variant.id))
        
        # Bind events
        text_widget.bind('<KeyRelease>', lambda e: self._on_variant_changed(variant.id, text_widget))
        text_widget.bind('<Button-1>', lambda e: self._select_variant(variant.id))
        text_widget.bind('<Button-3>', lambda e: context_menu.post(e.x_root, e.y_root))  # Right-click context menu
        
        # Store references (simplified)
        self.variant_text_widgets[variant.id] = {
            'frame': variant_frame,
            'text': text_widget,
            'context_menu': context_menu
        }
        
        # Add to paned window
        self.paned_window.add(variant_frame)
        
        # Highlight if active
        if variant.id == self.variant_group.active_variant_id:
            self._highlight_active_variant(variant.id)
    
    def _apply_highlighting(self, text_widget, content):
        """Apply syntax highlighting to a text widget - MUST match parent editor exactly."""
        import pygments
        
        # Clear existing tags
        for tag in text_widget.tag_names():
            if tag.startswith("Token"):
                text_widget.tag_delete(tag)
        
        # Copy EXACT colors from parent editor
        try:
            for tag in self.parent_codeview.tag_names():
                if tag.startswith("Token"):
                    try:
                        parent_config = self.parent_codeview.tag_config(tag)
                        if parent_config and isinstance(parent_config, dict):
                            if 'foreground' in parent_config:
                                fg_color = parent_config['foreground']
                                
                                # Extract actual color from tuple if needed
                                if isinstance(fg_color, tuple) and len(fg_color) >= 5:
                                    actual_color = fg_color[4]  # The actual color is at index 4
                                elif isinstance(fg_color, str):
                                    actual_color = fg_color
                                else:
                                    actual_color = None
                                
                                if actual_color and str(actual_color).strip():
                                    text_widget.tag_configure(tag, foreground=actual_color)
                    except Exception:
                        continue
        except Exception:
            pass
        
        # Apply syntax highlighting using parent's lexer
        try:
            start_index = "1.0"
            for token, text_content in pygments.lex(content, self.parent_codeview._lexer):
                if not text_content:
                    continue
                    
                token_str = str(token)
                end_index = text_widget.index(f"{start_index} + {len(text_content)}c")
                
                # Apply token tag (skip whitespace tokens)
                if token_str not in {"Token.Text.Whitespace", "Token.Text"}:
                    text_widget.tag_add(token_str, start_index, end_index)
                
                start_index = end_index
        except Exception as e:
            print(f"Syntax highlighting failed: {e}")
    
    def _highlight_active_variant(self, variant_id: str):
        """Highlight the active variant."""
        for vid, widget_info in self.variant_text_widgets.items():
            if vid == variant_id:
                widget_info['text'].configure(relief="solid", bd=2)
            else:
                widget_info['text'].configure(relief="sunken", bd=1)
    

    
    def _add_variant(self):
        """Add a new variant."""
        # Use active variant as base, or first variant
        base_variant_id = self.variant_group.active_variant_id or self.variant_group.variants[0].id
        base_content = self.variant_text_widgets[base_variant_id]['text'].get("1.0", "end-1c")
        
        variant = Variant(
            id=str(uuid.uuid4()),
            content=base_content,
            name=f"Variant {len(self.variant_group.variants) + 1}",
            start_line=self.variant_group.start_line,
            end_line=self.variant_group.end_line,
            start_col=self.variant_group.start_col,
            end_col=self.variant_group.end_col
        )
        
        self.variant_group.variants.append(variant)
        self._create_variant_view(variant)
        self._select_variant(variant.id)
        
        # Notify parent
        self.parent_codeview._on_variant_created(self.variant_group.id, variant.id)
    
    def _delete_variant(self, variant_id: str):
        """Delete a variant."""
        if len(self.variant_group.variants) <= 1:
            messagebox.showwarning("Cannot Delete", "Cannot delete the last variant.")
            return
        
        # Remove from data
        variant_to_remove = None
        for i, variant in enumerate(self.variant_group.variants):
            if variant.id == variant_id:
                variant_to_remove = variant
                del self.variant_group.variants[i]
                break
        
        if variant_to_remove:
            # Remove UI
            widget_info = self.variant_text_widgets.pop(variant_id)
            widget_info['frame'].destroy()
            
            # Update active variant
            if self.variant_group.active_variant_id == variant_id:
                self.variant_group.active_variant_id = self.variant_group.variants[0].id
                self._highlight_active_variant(self.variant_group.active_variant_id)
            
            # Notify parent
            self.parent_codeview._on_variant_deleted(self.variant_group.id, variant_id)
    
    def _select_variant(self, variant_id: str):
        """Select a variant as active."""
        self.variant_group.active_variant_id = variant_id
        self._highlight_active_variant(variant_id)
        
        # Notify parent
        self.parent_codeview._on_variant_selected(self.variant_group.id, variant_id)
    
    def _rename_variant(self, variant_id: str):
        """Rename a variant."""
        # Find the variant to get current name
        current_name = None
        for variant in self.variant_group.variants:
            if variant.id == variant_id:
                current_name = variant.name
                break
        
        if current_name is None:
            return
        
        # Prompt for new name
        from tkinter import simpledialog
        new_name = simpledialog.askstring("Rename Variant", f"Enter new name for '{current_name}':", initialvalue=current_name)
        
        if new_name and new_name.strip():
            # Update variant name
            for variant in self.variant_group.variants:
                if variant.id == variant_id:
                    variant.name = new_name.strip()
                    break
            
            # Update context menu
            if variant_id in self.variant_text_widgets:
                context_menu = self.variant_text_widgets[variant_id]['context_menu']
                context_menu.entryconfig(0, label=f"Rename '{new_name.strip()}'")
                context_menu.entryconfig(1, label=f"Delete '{new_name.strip()}'")
            
            # Notify parent
            self.parent_codeview._on_variant_renamed(self.variant_group.id, variant_id, new_name.strip())
    
    def _merge_selected(self):
        """Merge the selected variant back into main code."""
        if not self.variant_group.active_variant_id:
            messagebox.showwarning("No Selection", "Please select a variant to merge.")
            return
        
        # Get selected variant content
        active_content = self.variant_text_widgets[self.variant_group.active_variant_id]['text'].get("1.0", "end-1c")
        
        # Merge back
        self.parent_codeview._merge_variant(self.variant_group.id, self.variant_group.active_variant_id, active_content)
        
        # Close split view
        self._close_split()
    
    def _close_split(self):
        """Close the split view."""
        self.parent_codeview._close_split_view(self.variant_group.id)
    
    def _on_variant_changed(self, variant_id: str, text_widget):
        """Handle changes to variant content."""
        # Update variant content
        for variant in self.variant_group.variants:
            if variant.id == variant_id:
                variant.content = text_widget.get("1.0", "end-1c")
                break
        
        # Reapply highlighting
        self._apply_highlighting(text_widget, text_widget.get("1.0", "end-1c"))
        
        # Update heights of all variants to match the tallest one
        self._update_variant_heights()
        
        # Notify parent
        self.parent_codeview._on_variant_modified(self.variant_group.id, variant_id)
    
    def _update_variant_heights(self):
        """Update the height of all variant text widgets to match the tallest variant."""
        # Calculate the maximum height needed for all variants
        max_lines = 1
        for variant in self.variant_group.variants:
            lines = variant.content.count('\n') + 1
            max_lines = max(max_lines, lines)
        
        # Update height for all text widgets if it changed
        if max_lines != self.max_variant_height:
            self.max_variant_height = max_lines
            for widget_info in self.variant_text_widgets.values():
                widget_info['text'].configure(height=max_lines)


class ExploratoryCodeView(CodeView):
    """Enhanced CodeView with in-place variant splitting for exploratory programming."""
    
    def __init__(
        self,
        master: Misc | None = None,
        lexer: LexerType | None = None,
        color_scheme: dict[str, dict[str, str | int]] | str | None = None,
        on_variant_created: Optional[Callable[[str, str], None]] = None,
        on_variant_modified: Optional[Callable[[str, str], None]] = None,
        on_variant_deleted: Optional[Callable[[str, str], None]] = None,
        on_variant_selected: Optional[Callable[[str, str], None]] = None,
        on_variant_renamed: Optional[Callable[[str, str, str], None]] = None,
        on_variant_merged: Optional[Callable[[str, str, str], None]] = None,
        **kwargs,
    ) -> None:
        import pygments.lexers
        actual_lexer = lexer if lexer is not None else pygments.lexers.TextLexer
        super().__init__(master, actual_lexer, color_scheme, **kwargs)
        
        # Store current color scheme for variant views
        self._current_color_scheme = color_scheme
        
        # Callback functions
        self._on_variant_created_callback = on_variant_created
        self._on_variant_modified_callback = on_variant_modified
        self._on_variant_deleted_callback = on_variant_deleted
        self._on_variant_selected_callback = on_variant_selected
        self._on_variant_renamed_callback = on_variant_renamed
        self._on_variant_merged_callback = on_variant_merged
        
        # Variant management
        self.variant_groups: Dict[str, VariantGroup] = {}
        self.active_split_views: Dict[str, InPlaceSplitView] = {}
        self.split_positions: Dict[str, Tuple[int, int]] = {}  # group_id -> (start_line, end_line)
        
        # Enhanced context menu will be created automatically when needed
    
    def _create_context_menu(self) -> Menu:
        """Create an enhanced context menu with variant options."""
        # Call the parent implementation first
        context_menu = super()._create_context_menu()
        
        # Add separator and variant options
        context_menu.add_separator()
        context_menu.add_command(label="Create Variant", command=self._create_variant_from_selection)
        context_menu.add_command(label="Show All Variants", command=self._show_all_variants)
        
        return context_menu
    
    def _create_variant_from_selection(self):
        """Create a variant from the currently selected text and split the view in place."""
        try:
            # Check if there's a selection
            if not self.tag_ranges("sel"):
                messagebox.showwarning("No Selection", "Please select some code to create a variant.")
                return
            
            # Get selection
            start_idx = self.index("sel.first")
            end_idx = self.index("sel.last")
            selected_text = self.get(start_idx, end_idx)
            
            if not selected_text.strip():
                messagebox.showwarning("No Selection", "Please select some code to create a variant.")
                return
            
            # Parse indices
            start_line, start_col = map(int, start_idx.split('.'))
            end_line, end_col = map(int, end_idx.split('.'))
            
            # Create variant group
            group_id = str(uuid.uuid4())
            variant_group = VariantGroup(
                id=group_id,
                original_content=selected_text,
                start_line=start_line,
                end_line=end_line,
                start_col=start_col,
                end_col=end_col
            )
            
            # Create original variant
            original_variant = Variant(
                id=str(uuid.uuid4()),
                content=selected_text,
                name="Original",
                start_line=start_line,
                end_line=end_line,
                start_col=start_col,
                end_col=end_col
            )
            
            variant_group.variants.append(original_variant)
            variant_group.active_variant_id = original_variant.id
            
            # Store variant group
            self.variant_groups[group_id] = variant_group
            
            # Create in-place split view
            self._create_in_place_split(group_id)
            
        except Exception as e:
            print(f"Error creating variant: {e}")  # Debug print
            messagebox.showwarning("No Selection", f"Please select some code to create a variant. Error: {str(e)}")
    
    def _create_in_place_split(self, group_id: str):
        """Create an in-place split view for the variant group."""
        variant_group = self.variant_groups[group_id]
        
        # Calculate the position to insert the split view
        start_line = variant_group.start_line
        end_line = variant_group.end_line
        
        # Store the split position and the original text context
        self.split_positions[group_id] = (start_line, end_line)
        
        # Get the current text before and after the selection more carefully
        before_text = self.get("1.0", f"{start_line}.{variant_group.start_col}")
        after_text = self.get(f"{end_line}.{variant_group.end_col}", "end")
        
        
        # Store the context for proper reconstruction
        self.split_contexts = getattr(self, 'split_contexts', {})
        self.split_contexts[group_id] = {
            'before': before_text,
            'after': after_text,
            'original_selection': variant_group.original_content
        }
        
        # Create the split view
        split_view = InPlaceSplitView(self, variant_group, self)
        
        # Clear the main text widget
        self.delete("1.0", "end")
        
        # Insert content before selection
        if before_text:
            self.insert("1.0", before_text)
        
        # Insert the split view
        self.window_create("end", window=split_view)
        
        # Insert content after selection - no extra newline handling needed
        if after_text:
            self.insert("end", after_text)
        
        # Store reference
        self.active_split_views[group_id] = split_view
        
        # Force highlight update after creating variants
        self.highlight_all()
        print(self.get('20.0','20.5'))
        self.after(100, lambda: print("wah1"))
        self.after(2000, lambda: print("wah2"))
        
        
    
    def _close_split_view(self, group_id: str):
        """Close an in-place split view and restore normal editing."""
        if group_id not in self.active_split_views:
            return
        
        split_view = self.active_split_views[group_id]
        variant_group = self.variant_groups[group_id]
        
        # Get the current active variant content
        active_content = variant_group.original_content  # Default to original
        if variant_group.active_variant_id:
            for variant in variant_group.variants:
                if variant.id == variant_group.active_variant_id:
                    active_content = variant.content
                    break
        
        # Use stored context for proper reconstruction
        context = getattr(self, 'split_contexts', {}).get(group_id, {})
        before_text = context.get('before', '')
        after_text = context.get('after', '')
        
        # DEBUG: Print reconstruction info
        print(f"DEBUG: Closing split for group {group_id}")
        print(f"DEBUG: Before text ends with: {repr(before_text[-20:]) if before_text else 'None'}")
        print(f"DEBUG: Active content: {repr(active_content)}")
        print(f"DEBUG: After text starts with: {repr(after_text[:20]) if after_text else 'None'}")
        
        # Remove the split view first
        split_view.destroy()
        
        # Clear and reconstruct the text more carefully
        self.delete("1.0", "end")
        
        # Build the complete text ensuring proper line endings
        full_text = before_text + active_content + after_text
        
        # DEBUG: Print the reconstructed text around the merge point
        merge_point = len(before_text)
        print(f"DEBUG: Reconstructed text around merge point: {repr(full_text[max(0, merge_point-10):merge_point+50])}")
        
        # Insert the reconstructed text
        if full_text:
            self.insert("1.0", full_text)
        
        # Clean up
        del self.active_split_views[group_id]
        del self.variant_groups[group_id]
        del self.split_positions[group_id]
        if hasattr(self, 'split_contexts') and group_id in self.split_contexts:
            del self.split_contexts[group_id]
        
        # Force a complete rehighlight to fix any coloring issues
        self.after_idle(self.highlight_all)
        
        # DEBUG: Print final text to check for issues
        final_text = self.get("1.0", "end")
        print(f"DEBUG: Final text around merge point: {repr(final_text[max(0, merge_point-10):merge_point+50])}")
    
    def _merge_variant(self, group_id: str, variant_id: str, content: str):
        """Merge a variant back into the main text."""
        # The merge is handled by _close_split_view
        # Just notify the callback
        if self._on_variant_merged_callback:
            self._on_variant_merged_callback(group_id, variant_id, content)
    
    def _show_all_variants(self):
        """Show information about all variants."""
        if not self.variant_groups:
            messagebox.showinfo("No Variants", "No variants have been created yet.")
            return
        
        info = "Active Variants:\n\n"
        for group_id, group in self.variant_groups.items():
            info += f"Group {group_id[:8]}... (lines {group.start_line}-{group.end_line}):\n"
            for variant in group.variants:
                active = "★ " if variant.id == group.active_variant_id else "  "
                info += f"{active}{variant.name}\n"
            info += "\n"
        
        messagebox.showinfo("All Variants", info)
    
    # Callback methods
    def _on_variant_created(self, group_id: str, variant_id: str):
        """Handle variant creation."""
        if self._on_variant_created_callback:
            self._on_variant_created_callback(group_id, variant_id)
    
    def _on_variant_modified(self, group_id: str, variant_id: str):
        """Handle variant modification."""
        if self._on_variant_modified_callback:
            self._on_variant_modified_callback(group_id, variant_id)
    
    def _on_variant_deleted(self, group_id: str, variant_id: str):
        """Handle variant deletion."""
        if self._on_variant_deleted_callback:
            self._on_variant_deleted_callback(group_id, variant_id)
    
    def _on_variant_selected(self, group_id: str, variant_id: str):
        """Handle variant selection."""
        if self._on_variant_selected_callback:
            self._on_variant_selected_callback(group_id, variant_id)
    
    def _on_variant_renamed(self, group_id: str, variant_id: str, new_name: str):
        """Handle variant renaming."""
        if self._on_variant_renamed_callback:
            self._on_variant_renamed_callback(group_id, variant_id, new_name)
    
    # Public API
    def get_all_variants(self) -> Dict[str, VariantGroup]:
        """Get all variant groups."""
        return self.variant_groups.copy()
    
    def has_active_splits(self) -> bool:
        """Check if there are any active split views."""
        return len(self.active_split_views) > 0 