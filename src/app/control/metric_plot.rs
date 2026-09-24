use super::*;
use sha2::{Digest, Sha256};

impl OpenCADStudio {
    pub(super) fn control_export_metric_plot(
        &mut self,
        request: &Value,
    ) -> Result<Task<Message>, Value> {
        let raw_path = request["path"]
            .as_str()
            .ok_or_else(|| failure("path_required", "Supply an absolute PDF path"))?;
        let path = std::path::PathBuf::from(raw_path);
        if !path.is_absolute()
            || !path
                .extension()
                .and_then(|ext| ext.to_str())
                .is_some_and(|ext| ext.eq_ignore_ascii_case("pdf"))
        {
            return Err(failure(
                "invalid_pdf_path",
                "An absolute .pdf path is required",
            ));
        }
        if path.exists() {
            return Err(failure(
                "destination_exists",
                "PDF destination already exists",
            ));
        }
        if !path.parent().is_some_and(|parent| parent.is_dir()) {
            return Err(failure("parent_absent", "PDF parent directory must exist"));
        }
        let denominator = request["scale_denominator"]
            .as_u64()
            .filter(|value| (10..=1000).contains(value))
            .ok_or_else(|| failure("invalid_scale", "Scale denominator must be 10..1000"))?;
        let scene = &self.tabs[self.active_tab].scene;
        if scene.current_layout != "Model" || scene.document.header.insertion_units != 6 {
            return Err(failure(
                "metric_model_required",
                "Plot requires Model space and INSUNITS=6 metres",
            ));
        }
        let (min, max) = scene
            .model_space_extents()
            .ok_or_else(|| failure("empty_plot", "Model geometry has no printable extents"))?;
        let width_m = (max.x - min.x) as f64;
        let height_m = (max.y - min.y) as f64;
        let mm_per_unit = 1000.0 / denominator as f64;
        let clip_pad_m = 0.5 / mm_per_unit;
        if !width_m.is_finite()
            || !height_m.is_finite()
            || width_m <= 0.0
            || height_m <= 0.0
            || width_m * mm_per_unit + 1.0 > 277.0
            || height_m * mm_per_unit + 1.0 > 190.0
        {
            return Err(failure(
                "plot_exceeds_sheet",
                "Geometry exceeds A4 landscape with 10 mm margins",
            ));
        }
        let original = self.plot_dialog.clone();
        let mut profile = crate::ui::window::plot::PlotDialogState::default();
        profile.area = "Extents".into();
        profile.fit_to_paper = false;
        profile.scale = format!("{mm_per_unit}:1");
        profile.center = true;
        profile.to_file = true;
        profile.apply_plot_styles = false;
        self.plot_dialog = profile;
        // The ordinary Extents plot clips at the exact maximum point. A LINE
        // lying on that boundary can disappear in the PDF. Add 0.5 mm of
        // model-space window on each side without changing the requested scale.
        let page = self.area_plot_job((
            min.x as f64 - clip_pad_m,
            min.y as f64 - clip_pad_m,
            max.x as f64 + clip_pad_m,
            max.y as f64 + clip_pad_m,
        ));
        self.plot_dialog = original;
        let page =
            page.ok_or_else(|| failure("plot_unavailable", "Metric plot page could not be built"))?;
        if (page.paper_w - 297.0).abs() > 1e-6
            || (page.paper_h - 210.0).abs() > 1e-6
            || ((page.scale as f64) - mm_per_unit).abs() > 1e-5
        {
            return Err(failure(
                "plot_profile_mismatch",
                "Computed paper or scale differs from metric profile",
            ));
        }
        crate::io::pdf_export::export_pdf(&page, &path)
            .map_err(|error| failure("pdf_export_failed", &error))?;
        let data =
            std::fs::read(&path).map_err(|error| failure("pdf_read_failed", &error.to_string()))?;
        if !data.starts_with(b"%PDF-") || data.len() < 100 {
            return Err(failure(
                "pdf_invalid",
                "Export did not produce a PDF header",
            ));
        }
        let sha256 = format!("{:X}", Sha256::digest(&data));
        self.set_control_result(json!({
            "path":path,"sha256":sha256,"bytes":data.len(),
            "paper":"ISO_A4_LANDSCAPE","paper_mm":[297,210],
            "model_units":"m","scale_denominator":denominator,
            "mm_per_cad_unit":mm_per_unit,"min_margin_mm":10,
            "extent_m":[width_m,height_m],"plot_area":"Extents"
        }));
        Ok(Task::none())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn send(app: &mut OpenCADStudio, mut req: Value) -> Value {
        let state = app.control_state();
        req["protocol"] = json!(1);
        req["document_id"] = state["document_id"].clone();
        req["revision"] = state["revision"].clone();
        req["client_id"] = json!("plot-test");
        let (result, task) = app.control_request(req.clone());
        app.drive_headless_task(task).unwrap();
        if matches!(result["status"].as_str(), Some("accepted" | "running")) {
            app.control_request(json!({"op":"operation","request_id":req["request_id"]}))
                .0
        } else {
            result
        }
    }

    fn unique_pdf(directory: &std::path::Path) -> std::path::PathBuf {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        directory.join(format!("{}-{nanos}.pdf", std::process::id()))
    }

    #[test]
    fn metric_plot_is_scaled_and_replay_does_not_rewrite_pdf() {
        let mut app = OpenCADStudio::new_for_test();
        assert_eq!(app.automation_op(r#"{"op":"new"}"#)["ok"], true);
        for command in ["SETVAR INSUNITS 6", "LINE 0,0 4,0", "LINE 4,0 4,1"] {
            assert_eq!(
                app.automation_op(&json!({"op":"run","cmd":command}).to_string())["ok"],
                true
            );
        }
        let directory = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("target/mcp-isolated/metric-plot-tests");
        std::fs::create_dir_all(&directory).unwrap();
        let path = unique_pdf(&directory);
        let request = json!({"op":"metric_plot_pdf","request_id":"plot-1",
            "path":path,"scale_denominator":100});
        let state = app.control_state();
        let mut request = request;
        request["protocol"] = json!(1);
        request["document_id"] = state["document_id"].clone();
        request["revision"] = state["revision"].clone();
        request["client_id"] = json!("plot-test");
        let (first, task) = app.control_request(request.clone());
        app.drive_headless_task(task).unwrap();
        let first = if first["status"] == "completed" {
            first
        } else {
            app.control_request(json!({"op":"operation","request_id":"plot-1"}))
                .0
        };
        assert_eq!(first["status"], "completed", "{first}");
        assert_eq!(first["result"]["mm_per_cad_unit"], 10.0);
        assert_eq!(first["result"]["paper_mm"], json!([297, 210]));
        let bytes = std::fs::read(&path).unwrap();
        assert!(bytes.starts_with(b"%PDF-"));
        assert_eq!(app.control_request(request.clone()).0, first);
        assert_eq!(std::fs::read(&path).unwrap(), bytes);
        let mut second = request;
        second["request_id"] = json!("plot-2");
        assert_eq!(app.control_request(second).0["code"], "destination_exists");
        let too_large = send(
            &mut app,
            json!({"op":"metric_plot_pdf","request_id":"plot-3",
            "path":unique_pdf(&directory),
            "scale_denominator":10}),
        );
        assert_eq!(too_large["code"], "plot_exceeds_sheet", "{too_large}");
    }
}
