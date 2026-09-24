use super::*;
use sha2::{Digest, Sha256};

impl OpenCADStudio {
    pub(super) fn control_metric_page_setup(&self) -> Value {
        let scene = &self.tabs[self.active_tab].scene;
        let Some(settings) = scene.plot_settings_for("Model") else {
            return failure("page_setup_absent", "Model layout has no plot settings");
        };
        let ratio = settings.scale_numerator / settings.scale_denominator;
        json!({
            "ok":true,"layout":"Model","insertion_units":scene.document.header.insertion_units,
            "paper_size":settings.paper_size,"paper_mm":[settings.paper_width,settings.paper_height],
            "printer":settings.printer_name,
            "paper_units":settings.paper_units.to_code(),
            "rotation":settings.rotation.to_code(),"plot_type":settings.plot_type.to_code(),
            "scale_numerator":settings.scale_numerator,
            "scale_denominator":settings.scale_denominator,
            "scale_factor":settings.standard_scale_factor,
            "use_standard_scale":settings.flags.use_standard_scale,
            "plot_centered":settings.flags.plot_centered,
            "print_lineweights":settings.flags.print_lineweights,
            "margins_mm":[settings.margins.left,settings.margins.bottom,
                          settings.margins.right,settings.margins.top],
            "metric_scale_denominator": if ratio.is_finite() && ratio > 0.0 {
                Some(1000.0 / ratio)
            } else { None },
        })
    }

    pub(super) fn control_set_metric_page_setup(
        &mut self,
        request: &Value,
    ) -> Result<Task<Message>, Value> {
        use acadrust::objects::{PaperMargin, PlotPaperUnits, PlotRotation, PlotType, ScaledType};
        let denominator = request["scale_denominator"]
            .as_u64()
            .filter(|value| (10..=1000).contains(value))
            .ok_or_else(|| failure("invalid_scale", "Scale denominator must be 10..1000"))?;
        let i = self.active_tab;
        let scene = &self.tabs[i].scene;
        if scene.current_layout != "Model" || scene.document.header.insertion_units != 6 {
            return Err(failure(
                "metric_model_required",
                "Page setup requires Model and INSUNITS=6",
            ));
        }
        let mut settings = scene
            .plot_settings_for("Model")
            .ok_or_else(|| failure("page_setup_absent", "Model layout has no plot settings"))?;
        let paper = crate::io::paper_catalog::default_paper();
        let (width, height) = paper.portrait_mm();
        let mm_per_unit = 1000.0 / denominator as f64;
        settings.paper_size = paper.canonical.to_string();
        settings.printer_name = crate::io::plot_device::PlotDevice::None.canonical_name();
        settings.paper_width = width;
        settings.paper_height = height;
        settings.margins = PaperMargin::new(0.0, 0.0, 0.0, 0.0);
        settings.paper_units = PlotPaperUnits::Millimeters;
        settings.rotation = PlotRotation::Degrees90;
        settings.plot_type = PlotType::Extents;
        settings.scale_type = ScaledType::CustomScale;
        settings.scale_numerator = mm_per_unit;
        settings.scale_denominator = 1.0;
        settings.standard_scale_factor = mm_per_unit * 25.4;
        settings.flags.use_standard_scale = false;
        settings.flags.plot_centered = true;
        settings.flags.print_lineweights = true;
        settings.flags.scale_lineweights = false;
        settings.flags.plot_plot_styles = false;
        settings.flags.show_plot_styles = false;
        settings.origin_x = 0.0;
        settings.origin_y = 0.0;
        self.push_undo_snapshot(i, "MCP METRIC PAGE SETUP");
        if !self.tabs[i]
            .scene
            .set_layout_plot_settings("Model", &settings)
        {
            self.discard_last_undo_entry(i);
            return Err(failure(
                "page_setup_failed",
                "Model page setup could not be written",
            ));
        }
        self.tabs[i].dirty = true;
        self.set_control_result(json!({"layout":"Model","paper":"ISO_A4_LANDSCAPE",
            "scale_denominator":denominator,"mm_per_cad_unit":mm_per_unit,
            "page_setup":self.control_metric_page_setup()}));
        Ok(Task::none())
    }

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
        if request["require_page_setup"] == true {
            use acadrust::objects::{PlotPaperUnits, PlotRotation, PlotType};
            let setup = self.control_metric_page_setup();
            let expected = request["scale_denominator"].as_u64().unwrap_or(0) as f64;
            if setup["ok"] != true
                || setup["metric_scale_denominator"]
                    .as_f64()
                    .is_none_or(|observed| (observed - expected).abs() > 1e-6)
                || setup["paper_mm"] != json!([210.0, 297.0])
                || setup["paper_size"].as_str()
                    != Some(crate::io::paper_catalog::default_paper().canonical.as_ref())
                || setup["printer"] != crate::io::plot_device::PlotDevice::None.canonical_name()
                || setup["insertion_units"] != 6
                || setup["paper_units"] != PlotPaperUnits::Millimeters.to_code()
                || setup["rotation"] != PlotRotation::Degrees90.to_code()
                || setup["plot_type"] != PlotType::Extents.to_code()
                || setup["use_standard_scale"] != false
                || setup["plot_centered"] != true
                || setup["print_lineweights"] != true
                || setup["scale_numerator"]
                    .as_f64()
                    .is_none_or(|observed| (observed - 1000.0 / expected).abs() > 1e-6)
                || setup["scale_denominator"] != 1.0
                || setup["margins_mm"] != json!([0.0, 0.0, 0.0, 0.0])
                || setup["scale_factor"]
                    .as_f64()
                    .is_none_or(|observed| (observed - 25.4 * 1000.0 / expected).abs() > 1e-6)
            {
                return Err(failure(
                    "page_setup_mismatch",
                    "Stored Model page setup differs from PDF profile",
                ));
            }
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

    #[test]
    fn metric_page_setup_is_typed_readable_and_undoable() {
        let mut app = OpenCADStudio::new_for_test();
        assert_eq!(app.automation_op(r#"{"op":"new"}"#)["ok"], true);
        assert_eq!(
            app.automation_op(r#"{"op":"run","cmd":"SETVAR INSUNITS 6"}"#)["ok"],
            true
        );
        let initial = app.control_request(json!({"op":"metric_page_setup"})).0;
        assert_eq!(initial["ok"], true);
        let changed = send(
            &mut app,
            json!({"op":"set_metric_page_setup",
            "request_id":"page-setup-1","scale_denominator":100}),
        );
        assert_eq!(changed["status"], "completed", "{changed}");
        let stored = app.control_request(json!({"op":"metric_page_setup"})).0;
        assert_eq!(stored["paper_mm"], json!([210.0, 297.0]));
        assert_eq!(stored["metric_scale_denominator"], 100.0);
        assert_eq!(stored["scale_numerator"], 10.0);
        assert_eq!(stored["scale_denominator"], 1.0);
        assert_eq!(stored["scale_factor"], 254.0);
        assert_eq!(stored["plot_centered"], true);
        assert_eq!(stored["use_standard_scale"], false);
        let undone = send(&mut app, json!({"op":"undo","request_id":"page-undo-1"}));
        assert_eq!(undone["status"], "completed", "{undone}");
        assert_eq!(
            app.control_request(json!({"op":"metric_page_setup"})).0,
            initial
        );
    }
}
