//! One guarded four-edge wall thickness edit, committed in one GUI operation.
use super::{Message, OpenCADStudio, failure};
use acadrust::{EntityType, Handle};
use iced::Task;
use serde_json::{Value, json};

const EPS: f64 = 1e-6;

impl OpenCADStudio {
    pub(super) fn control_edit_wall_thickness(
        &mut self,
        request: &Value,
    ) -> Result<Task<Message>, Value> {
        let raw = request["edge_handles"].as_array().filter(|values| values.len() == 4)
            .ok_or_else(|| failure("wall_edges_required", "Supply four ordered edge handles"))?;
        let mut handles = Vec::with_capacity(4);
        for value in raw {
            let text = value.as_str().ok_or_else(|| failure("invalid_handle", "Expected hexadecimal handle"))?;
            let number = u64::from_str_radix(text.trim_start_matches("0x"), 16)
                .map_err(|_| failure("invalid_handle", "Expected hexadecimal handle"))?;
            let handle = Handle::new(number);
            if handles.contains(&handle) {
                return Err(failure("duplicate_wall_edge", "Wall edges must be distinct"));
            }
            handles.push(handle);
        }
        let expected = request["expected_thickness_m"].as_f64()
            .ok_or_else(|| failure("thickness_required", "Expected thickness is required"))?;
        let desired = request["new_thickness_m"].as_f64()
            .ok_or_else(|| failure("thickness_required", "New thickness is required"))?;
        if !expected.is_finite() || !desired.is_finite() ||
            !(0.01..=10.0).contains(&expected) || !(0.01..=10.0).contains(&desired) ||
            (expected - desired).abs() <= EPS {
            return Err(failure("invalid_thickness", "Thickness must change within 0.01..10 m"));
        }
        let i = self.active_tab;
        let mut lines = Vec::with_capacity(4);
        for handle in &handles {
            if self.tabs[i].scene.is_layer_locked(*handle) {
                return Err(failure("layer_locked", "Wall edge is on a locked layer"));
            }
            let Some(EntityType::Line(line)) = self.tabs[i].scene.document.get_entity(*handle) else {
                return Err(failure("wall_edge_invalid", "Each ordered wall edge must be a LINE"));
            };
            if ![line.start.x, line.start.y, line.start.z,
                  line.end.x, line.end.y, line.end.z].iter().all(|value| value.is_finite()) ||
                line.start.z.abs() > EPS || line.end.z.abs() > EPS {
                return Err(failure("wall_edge_invalid", "Wall edges must be finite 2D lines"));
            }
            lines.push(line.clone());
        }
        if lines.iter().any(|line| line.common.layer != lines[0].common.layer ||
                              line.common.owner_handle != lines[0].common.owner_handle) ||
            (0..4).any(|index| (lines[index].end - lines[(index + 1) % 4].start).length() > EPS) {
            return Err(failure("wall_outline_invalid", "Wall edges must form one closed outline"));
        }
        let a = lines[0].start;
        let b = lines[0].end;
        let c = lines[2].start;
        let d = lines[2].end;
        let horizontal = (a.y - b.y).abs() <= EPS && (a.x - b.x).abs() > EPS &&
            (c.y - d.y).abs() <= EPS && (a.x - d.x).abs() <= EPS && (b.x - c.x).abs() <= EPS;
        let vertical = (a.x - b.x).abs() <= EPS && (a.y - b.y).abs() > EPS &&
            (c.x - d.x).abs() <= EPS && (a.y - d.y).abs() <= EPS && (b.y - c.y).abs() <= EPS;
        if !horizontal && !vertical {
            return Err(failure("wall_outline_invalid", "Only an axis-aligned four-edge wall is supported"));
        }
        let first = if horizontal { a.y } else { a.x };
        let second = if horizontal { c.y } else { c.x };
        let old_thickness = (first - second).abs();
        if old_thickness <= EPS || (old_thickness - expected).abs() > EPS {
            return Err(failure("wall_thickness_stale", "Wall thickness differs from the expected value"));
        }
        let center = (first + second) / 2.0;
        let sign = (first - second).signum();
        let first_new = center + sign * desired / 2.0;
        let second_new = center - sign * desired / 2.0;
        let original = lines.clone();
        for (index, line) in lines.iter_mut().enumerate() {
            let (start_normal, end_normal) = match index {
                0 => (first_new, first_new),
                1 => (first_new, second_new),
                2 => (second_new, second_new),
                _ => (second_new, first_new),
            };
            if horizontal {
                line.start.y = start_normal;
                line.end.y = end_normal;
            } else {
                line.start.x = start_normal;
                line.end.x = end_normal;
            }
        }
        self.push_undo_snapshot(i, "MCP EDIT_WALL_THICKNESS");
        for (index, line) in lines.into_iter().enumerate() {
            if !self.tabs[i].scene.update_entity(EntityType::Line(line)) {
                for old in original.into_iter().take(index).rev() {
                    if !self.tabs[i].scene.update_entity(EntityType::Line(old)) {
                        return Err(failure("wall_rollback_failed", "Wall edit could not be rolled back"));
                    }
                }
                self.discard_last_undo_entry(i);
                return Err(failure("wall_update_failed", "Wall edit was rolled back"));
            }
        }
        self.tabs[i].dirty = true;
        self.refresh_properties();
        self.set_control_result(json!({"wall_edges":raw,"old_thickness_m":old_thickness,
            "new_thickness_m":desired,"orientation":if horizontal { "horizontal" } else { "vertical" },
            "closed_outline":true}));
        Ok(Task::none())
    }

    pub(super) fn control_edit_wall_length(
        &mut self,
        request: &Value,
    ) -> Result<Task<Message>, Value> {
        let raw = request["edge_handles"].as_array().filter(|values| values.len() == 4)
            .ok_or_else(|| failure("wall_edges_required", "Supply four ordered edge handles"))?;
        let mut handles = Vec::with_capacity(4);
        for value in raw {
            let text = value.as_str().ok_or_else(|| failure("invalid_handle", "Expected hexadecimal handle"))?;
            let number = u64::from_str_radix(text.trim_start_matches("0x"), 16)
                .map_err(|_| failure("invalid_handle", "Expected hexadecimal handle"))?;
            let handle = Handle::new(number);
            if handles.contains(&handle) {
                return Err(failure("duplicate_wall_edge", "Wall edges must be distinct"));
            }
            handles.push(handle);
        }
        let dimension_text = request["dimension_handle"].as_str()
            .ok_or_else(|| failure("dimension_required", "Supply the associated dimension handle"))?;
        let dimension_number = u64::from_str_radix(dimension_text.trim_start_matches("0x"), 16)
            .map_err(|_| failure("invalid_handle", "Expected hexadecimal dimension handle"))?;
        let dimension_handle = Handle::new(dimension_number);
        if handles.contains(&dimension_handle) {
            return Err(failure("dimension_invalid", "Dimension handle is a wall edge"));
        }
        let expected = request["expected_length_m"].as_f64()
            .ok_or_else(|| failure("length_required", "Expected wall length is required"))?;
        let desired = request["new_length_m"].as_f64()
            .ok_or_else(|| failure("length_required", "New wall length is required"))?;
        let expected_thickness = request["expected_thickness_m"].as_f64()
            .ok_or_else(|| failure("thickness_required", "Expected wall thickness is required"))?;
        if !expected.is_finite() || !desired.is_finite() || !expected_thickness.is_finite() ||
            !(0.1..=1000.0).contains(&expected) || !(0.1..=1000.0).contains(&desired) ||
            !(0.01..=10.0).contains(&expected_thickness) || (desired - expected).abs() <= EPS {
            return Err(failure("invalid_length", "Length must change within 0.1..1000 m"));
        }
        let i = self.active_tab;
        let mut lines = Vec::with_capacity(4);
        for handle in &handles {
            if self.tabs[i].scene.is_layer_locked(*handle) {
                return Err(failure("layer_locked", "Wall edge is on a locked layer"));
            }
            let Some(EntityType::Line(line)) = self.tabs[i].scene.document.get_entity(*handle) else {
                return Err(failure("wall_edge_invalid", "Each ordered wall edge must be a LINE"));
            };
            if ![line.start.x, line.start.y, line.start.z,
                  line.end.x, line.end.y, line.end.z].iter().all(|value| value.is_finite()) ||
                line.start.z.abs() > EPS || line.end.z.abs() > EPS {
                return Err(failure("wall_edge_invalid", "Wall edges must be finite 2D lines"));
            }
            lines.push(line.clone());
        }
        if lines.iter().any(|line| line.common.layer != lines[0].common.layer ||
                              line.common.owner_handle != lines[0].common.owner_handle) ||
            (0..4).any(|index| (lines[index].end - lines[(index + 1) % 4].start).length() > EPS) {
            return Err(failure("wall_outline_invalid", "Wall edges must form one closed outline"));
        }
        let model_owner = lines[0].common.owner_handle;
        if self.tabs[i].scene.document.entities().any(|entity| {
            let common = entity.common();
            common.owner_handle == model_owner &&
                !handles.contains(&common.handle) && common.handle != dimension_handle
        }) {
            return Err(failure("wall_context_unsupported",
                "Length edit requires an isolated four-edge wall and one dimension"));
        }
        let a = lines[0].start;
        let b = lines[0].end;
        let c = lines[1].end;
        let d = lines[2].end;
        let along = b - a;
        let width = c - b;
        let old_length = along.length();
        let old_thickness = width.length();
        if old_length <= EPS || old_thickness <= EPS ||
            (old_length - expected).abs() > EPS ||
            (old_thickness - expected_thickness).abs() > EPS {
            return Err(failure("wall_length_stale", "Wall length or thickness differs"));
        }
        if (c - d - along).length() > EPS || (d - a - width).length() > EPS ||
            along.dot(&width).abs() > EPS * old_length * old_thickness {
            return Err(failure("wall_outline_invalid", "Wall must be one orthogonal rectangle"));
        }
        if self.tabs[i].scene.is_layer_locked(dimension_handle) {
            return Err(failure("layer_locked", "Dimension is on a locked layer"));
        }
        let Some(EntityType::Dimension(dimension)) =
            self.tabs[i].scene.document.get_entity(dimension_handle) else {
            return Err(failure("dimension_invalid", "Associated dimension is absent"));
        };
        if (dimension.base().actual_measurement - expected).abs() > EPS {
            return Err(failure("dimension_stale", "Dimension measurement differs"));
        }
        let sources = self.tabs[i].scene.dimension_association_sources(dimension_handle);
        if sources.len() != 2 || !sources.contains(&handles[1]) || !sources.contains(&handles[3]) {
            return Err(failure("dimension_unbound", "Dimension must reference both wall caps"));
        }
        let displacement = along * ((desired - old_length) / old_length);
        let original = lines.clone();
        lines[0].end = lines[0].end + displacement;
        lines[1].start = lines[1].start + displacement;
        lines[1].end = lines[1].end + displacement;
        lines[2].start = lines[2].start + displacement;
        self.push_undo_snapshot(i, "MCP EDIT_WALL_LENGTH");
        for (index, line) in lines.into_iter().enumerate().take(3) {
            if !self.tabs[i].scene.update_entity(EntityType::Line(line)) {
                for old in original.iter().take(index).rev() {
                    if !self.tabs[i].scene.update_entity(EntityType::Line(old.clone())) {
                        return Err(failure("wall_rollback_failed", "Wall edit could not be rolled back"));
                    }
                }
                self.discard_last_undo_entry(i);
                return Err(failure("wall_update_failed", "Wall edit was rolled back"));
            }
        }
        let measured = match self.tabs[i].scene.document.get_entity(dimension_handle) {
            Some(EntityType::Dimension(value)) => value.base().actual_measurement,
            _ => f64::NAN,
        };
        if !measured.is_finite() || (measured - desired).abs() > EPS {
            for old in original.iter().take(3).rev() {
                if !self.tabs[i].scene.update_entity(EntityType::Line(old.clone())) {
                    return Err(failure("wall_rollback_failed", "Wall edit could not be rolled back"));
                }
            }
            self.discard_last_undo_entry(i);
            return Err(failure("dimension_update_failed", "Dimension did not follow wall length"));
        }
        self.tabs[i].dirty = true;
        self.refresh_properties();
        self.set_control_result(json!({"wall_edges":raw,"dimension_handle":dimension_text,
            "old_length_m":old_length,"new_length_m":desired,
            "thickness_m":old_thickness,"closed_outline":true,
            "dimension_measurement_m":measured}));
        Ok(Task::none())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn request(app: &mut OpenCADStudio, mut value: Value) -> Value {
        let state = app.control_state();
        value["protocol"] = json!(1);
        value["document_id"] = state["document_id"].clone();
        value["revision"] = state["revision"].clone();
        value["request_id"] = json!(format!("wall-{}", app.control.serial));
        let (result, task) = app.control_request(value.clone());
        app.drive_headless_task(task).unwrap();
        if matches!(result["status"].as_str(), Some("accepted" | "running")) {
            app.control_request(json!({"op":"operation","request_id":value["request_id"]})).0
        } else {
            result
        }
    }

    fn fixture(vertical: bool) -> (OpenCADStudio, Vec<String>, Handle) {
        let mut app = OpenCADStudio::new_for_test();
        assert_eq!(app.automation_op(r#"{"op":"new"}"#)["ok"], true);
        let commands = if vertical {
            ["LINE -0.1,0 -0.1,4", "LINE -0.1,4 0.1,4",
             "LINE 0.1,4 0.1,0", "LINE 0.1,0 -0.1,0",
             "DIMLINEAR -0.1,2 0.1,2 0,4.5"]
        } else {
            ["LINE 0,0.1 4,0.1", "LINE 4,0.1 4,-0.1",
             "LINE 4,-0.1 0,-0.1", "LINE 0,-0.1 0,0.1",
             "DIMLINEAR 2,0.1 2,-0.1 4.5,0"]
        };
        for command in commands {
            let result = app.automation_op(&json!({"op":"run","cmd":command}).to_string());
            assert_eq!(result["ok"], true, "{command}: {result}");
        }
        let mut edges: Vec<_> = app.tabs[app.active_tab].scene.document.entities()
            .filter_map(|entity| match entity {
                EntityType::Line(line) => Some(line.common.handle),
                _ => None,
            }).collect();
        edges.sort_by_key(|handle| handle.value());
        let dimension = app.tabs[app.active_tab].scene.document.entities()
            .find_map(|entity| match entity {
                EntityType::Dimension(dimension) => Some(dimension.base().common.handle),
                _ => None,
            }).unwrap();
        assert_eq!(edges.len(), 4);
        let text = edges.iter().map(|handle| format!("{:X}", handle.value())).collect();
        (app, text, dimension)
    }

    #[test]
    fn guarded_wall_edit_is_closed_associative_and_one_undo_for_both_axes() {
        for vertical in [false, true] {
            let (mut app, edges, dimension) = fixture(vertical);
            let before = app.control_state()["geometry_revision"].as_u64().unwrap();
            let bad = request(&mut app, json!({"op":"edit_wall_thickness",
                "edge_handles":edges,"expected_thickness_m":0.3,"new_thickness_m":0.25}));
            assert_eq!(bad["code"], "wall_thickness_stale", "{bad}");
            assert_eq!(app.control_state()["geometry_revision"], before);
            let mut reordered = edges.clone();
            reordered.swap(1, 2);
            let bad = request(&mut app, json!({"op":"edit_wall_thickness",
                "edge_handles":reordered,"expected_thickness_m":0.2,"new_thickness_m":0.25}));
            assert_eq!(bad["code"], "wall_outline_invalid", "{bad}");
            assert_eq!(app.control_state()["geometry_revision"], before);
            let changed = request(&mut app, json!({"op":"edit_wall_thickness",
                "edge_handles":edges,"expected_thickness_m":0.2,"new_thickness_m":0.25}));
            assert_eq!(changed["ok"], true, "{changed}");
            assert_eq!(changed["result"]["closed_outline"], true);
            let scene = &app.tabs[app.active_tab].scene;
            let mut lines = Vec::new();
            for edge in &edges {
                let handle = Handle::new(u64::from_str_radix(edge, 16).unwrap());
                let Some(EntityType::Line(line)) = scene.document.get_entity(handle) else { panic!() };
                lines.push(line);
            }
            for index in 0..4 {
                assert!((lines[index].end - lines[(index + 1) % 4].start).length() < EPS);
            }
            let distance = if vertical {
                (lines[0].start.x - lines[2].start.x).abs()
            } else {
                (lines[0].start.y - lines[2].start.y).abs()
            };
            assert!((distance - 0.25).abs() < EPS);
            let Some(EntityType::Dimension(dimension_entity)) = scene.document.get_entity(dimension) else { panic!() };
            assert!((dimension_entity.base().actual_measurement - 0.25).abs() < EPS);
            let first_handle = lines[0].common.handle;
            let opposite_handle = lines[2].common.handle;
            assert_eq!(scene.dimension_association_sources(dimension),
                vec![first_handle, opposite_handle]);
            let undone = request(&mut app, json!({"op":"undo"}));
            assert_eq!(undone["ok"], true, "{undone}");
            let scene = &app.tabs[app.active_tab].scene;
            let Some(EntityType::Line(first)) = scene.document.get_entity(first_handle) else { panic!() };
            let Some(EntityType::Line(opposite)) = scene.document.get_entity(opposite_handle) else { panic!() };
            let distance = if vertical { (first.start.x - opposite.start.x).abs() }
                           else { (first.start.y - opposite.start.y).abs() };
            assert!((distance - 0.2).abs() < EPS);
        }
    }

    #[test]
    fn guarded_length_edit_preserves_caps_and_updates_native_dimension() {
        for aligned in [false, true] {
            let mut app = OpenCADStudio::new_for_test();
            assert_eq!(app.automation_op(r#"{"op":"new"}"#)["ok"], true);
            let commands: &[&str] = if aligned {
                &["LINE -0.08,0.06 2.92,4.06", "LINE 2.92,4.06 3.08,3.94",
                  "LINE 3.08,3.94 0.08,-0.06", "LINE 0.08,-0.06 -0.08,0.06",
                  "DIMALIGNED 0,0 3,4 1.1,2.3"]
            } else {
                &["LINE 0,0.1 4,0.1", "LINE 4,0.1 4,-0.1",
                  "LINE 4,-0.1 0,-0.1", "LINE 0,-0.1 0,0.1",
                  "DIMLINEAR 0,0 4,0 2,0.5"]
            };
            for command in commands {
                let result = app.automation_op(&json!({"op":"run","cmd":command}).to_string());
                assert_eq!(result["ok"], true, "{command}: {result}");
            }
            let mut edges: Vec<_> = app.tabs[app.active_tab].scene.document.entities()
                .filter_map(|entity| match entity {
                    EntityType::Line(line) => Some(line.common.handle), _ => None,
                }).collect();
            edges.sort_by_key(|handle| handle.value());
            let dimension = app.tabs[app.active_tab].scene.document.entities()
                .find_map(|entity| match entity {
                    EntityType::Dimension(value) => Some(value.base().common.handle), _ => None,
                }).unwrap();
            assert_eq!(edges.len(), 4);
            let texts: Vec<_> = edges.iter().map(|handle| format!("{:X}", handle.value())).collect();
            let old_length = if aligned { 5.0 } else { 4.0 };
            let new_length = old_length + 0.5;
            let sources = app.tabs[app.active_tab].scene.dimension_association_sources(dimension);
            assert_eq!(sources.len(), 2);
            assert!(sources.contains(&edges[1]) && sources.contains(&edges[3]));
            let before_revision = app.control_state()["geometry_revision"].as_u64().unwrap();
            let bad = request(&mut app, json!({"op":"edit_wall_length", "edge_handles":texts,
                "dimension_handle":format!("{:X}",dimension.value()),
                "expected_length_m":old_length+0.1,"new_length_m":new_length,
                "expected_thickness_m":0.2}));
            assert_eq!(bad["code"], "wall_length_stale", "{bad}");
            assert_eq!(app.control_state()["geometry_revision"], before_revision);
            let changed = request(&mut app, json!({"op":"edit_wall_length", "edge_handles":texts,
                "dimension_handle":format!("{:X}",dimension.value()),
                "expected_length_m":old_length,"new_length_m":new_length,
                "expected_thickness_m":0.2}));
            assert_eq!(changed["ok"], true, "{changed}");
            assert_eq!(changed["result"]["closed_outline"], true);
            let scene = &app.tabs[app.active_tab].scene;
            let lines: Vec<_> = edges.iter().map(|handle| match scene.document.get_entity(*handle) {
                Some(EntityType::Line(line)) => line.clone(), _ => panic!("line absent"),
            }).collect();
            for index in 0..4 {
                assert!((lines[index].end - lines[(index+1)%4].start).length() < EPS);
            }
            assert!(((lines[0].end - lines[0].start).length() - new_length).abs() < EPS);
            let Some(EntityType::Dimension(value)) = scene.document.get_entity(dimension) else { panic!() };
            assert!((value.base().actual_measurement - new_length).abs() < EPS);
            let undone = request(&mut app, json!({"op":"undo"}));
            assert_eq!(undone["ok"], true, "{undone}");
            let Some(EntityType::Dimension(value)) =
                app.tabs[app.active_tab].scene.document.get_entity(dimension) else { panic!() };
            assert!((value.base().actual_measurement - old_length).abs() < EPS);
        }
    }

    #[test]
    fn guarded_length_edit_rejects_unmodeled_context() {
        let mut app = OpenCADStudio::new_for_test();
        assert_eq!(app.automation_op(r#"{"op":"new"}"#)["ok"], true);
        for command in ["LINE 0,0.1 4,0.1", "LINE 4,0.1 4,-0.1",
                        "LINE 4,-0.1 0,-0.1", "LINE 0,-0.1 0,0.1",
                        "DIMLINEAR 0,0 4,0 2,0.5", "LINE 9,9 10,10"] {
            assert_eq!(app.automation_op(&json!({"op":"run","cmd":command}).to_string())["ok"], true);
        }
        let mut lines: Vec<_> = app.tabs[app.active_tab].scene.document.entities()
            .filter_map(|entity| match entity { EntityType::Line(value) =>
                Some(value.common.handle), _ => None }).collect();
        lines.sort_by_key(|handle| handle.value());
        let dimension = app.tabs[app.active_tab].scene.document.entities()
            .find_map(|entity| match entity { EntityType::Dimension(value) =>
                Some(value.base().common.handle), _ => None }).unwrap();
        let before = app.control_state()["geometry_revision"].clone();
        let rejected = request(&mut app, json!({"op":"edit_wall_length",
            "edge_handles":lines[..4].iter().map(|h| format!("{:X}",h.value())).collect::<Vec<_>>(),
            "dimension_handle":format!("{:X}",dimension.value()),
            "expected_length_m":4,"new_length_m":4.5,"expected_thickness_m":0.2}));
        assert_eq!(rejected["code"], "wall_context_unsupported", "{rejected}");
        assert_eq!(app.control_state()["geometry_revision"], before);
    }
}
