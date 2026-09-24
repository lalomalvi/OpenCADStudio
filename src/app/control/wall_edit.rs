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
}
