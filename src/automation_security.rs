//! Private local automation descriptors. The descriptor includes a bearer token.

use std::{fs::File, io, path::Path};

#[cfg(windows)]
const PRIVATE_DACL: &str = "D:P(A;;FA;;;OW)(A;;FA;;;SY)";

#[cfg(windows)]
fn wide_path(path: &Path) -> io::Result<Vec<u16>> {
    use std::os::windows::ffi::OsStrExt;
    let parent = path.parent().ok_or_else(|| io::Error::other("Descriptor has no parent"))?
        .canonicalize()?;
    let name = path.file_name().ok_or_else(|| io::Error::other("Descriptor has no filename"))?;
    let absolute = parent.join(name);
    let text = absolute.to_string_lossy();
    let verbatim = if text.starts_with(r"\\?\") { text.into_owned() }
        else if let Some(unc) = text.strip_prefix(r"\\") { format!(r"\\?\UNC\{unc}") }
        else { format!(r"\\?\{text}") };
    Ok(std::ffi::OsStr::new(&verbatim).encode_wide().chain(std::iter::once(0)).collect())
}

#[cfg(windows)]
pub(crate) fn create_private_file(path: &Path) -> io::Result<File> {
    use std::os::windows::{ffi::OsStrExt, io::{FromRawHandle, RawHandle}};
    use windows_sys::Win32::{
        Foundation::{GENERIC_WRITE, INVALID_HANDLE_VALUE, LocalFree},
        Security::{Authorization::{ConvertStringSecurityDescriptorToSecurityDescriptorW,
                                   SDDL_REVISION_1}, SECURITY_ATTRIBUTES},
        Storage::FileSystem::{CreateFileW, CREATE_NEW, FILE_ATTRIBUTE_NORMAL},
    };
    let name = wide_path(path)?;
    let sddl: Vec<u16> = std::ffi::OsStr::new(PRIVATE_DACL).encode_wide()
        .chain(std::iter::once(0)).collect();
    let mut descriptor = std::ptr::null_mut();
    if unsafe { ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl.as_ptr(), SDDL_REVISION_1, &mut descriptor, std::ptr::null_mut()) } == 0 {
        return Err(io::Error::last_os_error());
    }
    let attributes = SECURITY_ATTRIBUTES {
        nLength: std::mem::size_of::<SECURITY_ATTRIBUTES>() as u32,
        lpSecurityDescriptor: descriptor, bInheritHandle: 0,
    };
    let handle = unsafe { CreateFileW(name.as_ptr(), GENERIC_WRITE, 0, &attributes,
        CREATE_NEW, FILE_ATTRIBUTE_NORMAL, std::ptr::null_mut()) };
    let error = if handle == INVALID_HANDLE_VALUE { Some(io::Error::last_os_error()) } else { None };
    unsafe { LocalFree(descriptor) };
    if let Some(error) = error { return Err(error); }
    Ok(unsafe { File::from_raw_handle(handle as RawHandle) })
}

#[cfg(unix)]
pub(crate) fn create_private_file(path: &Path) -> io::Result<File> {
    use std::os::unix::fs::OpenOptionsExt;
    std::fs::OpenOptions::new().write(true).create_new(true).mode(0o600).open(path)
}

#[cfg(not(any(unix, windows)))]
pub(crate) fn create_private_file(path: &Path) -> io::Result<File> {
    std::fs::OpenOptions::new().write(true).create_new(true).open(path)
}

#[cfg(windows)]
pub(crate) fn private_file(path: &Path) -> bool {
    use windows_sys::Win32::{
        Foundation::LocalFree,
        Security::{Authorization::{ConvertSecurityDescriptorToStringSecurityDescriptorW,
                                   SDDL_REVISION_1}, DACL_SECURITY_INFORMATION,
                   GetFileSecurityW},
    };
    let Ok(name) = wide_path(path) else { return false; };
    let mut required = 0;
    unsafe { GetFileSecurityW(name.as_ptr(), DACL_SECURITY_INFORMATION,
        std::ptr::null_mut(), 0, &mut required) };
    if required == 0 || required > 65_536 { return false; }
    let mut buffer = vec![0u8; required as usize];
    if unsafe { GetFileSecurityW(name.as_ptr(), DACL_SECURITY_INFORMATION,
        buffer.as_mut_ptr().cast(), required, &mut required) } == 0 { return false; }
    let mut output: *mut u16 = std::ptr::null_mut();
    let mut length = 0;
    if unsafe { ConvertSecurityDescriptorToStringSecurityDescriptorW(
        buffer.as_mut_ptr().cast(), SDDL_REVISION_1, DACL_SECURITY_INFORMATION,
        &mut output, &mut length) } == 0 { return false; }
    let actual = unsafe { String::from_utf16_lossy(std::slice::from_raw_parts(output, length as usize)) };
    unsafe { LocalFree(output.cast()) };
    let actual = actual.trim_end_matches('\0');
    actual.ends_with(PRIVATE_DACL) || actual.ends_with("D:P(A;;FA;;;SY)(A;;FA;;;OW)")
}

#[cfg(all(test, windows))]
mod tests {
    use super::*;
    use std::{io::Write, os::windows::ffi::OsStrExt};
    use windows_sys::Win32::{
        Foundation::LocalFree,
        Security::{Authorization::{ConvertStringSecurityDescriptorToSecurityDescriptorW,
                                   SDDL_REVISION_1}, DACL_SECURITY_INFORMATION,
                   PROTECTED_DACL_SECURITY_INFORMATION, SetFileSecurityW},
    };

    #[test]
    fn descriptor_acl_is_private_and_broader_acl_is_rejected() {
        let root = std::env::current_dir().unwrap().join("target/mcp-acl-tests")
            .join(format!("{}", std::process::id()));
        std::fs::create_dir_all(&root).unwrap();
        let path = root.join("synthetic.json");
        let mut file = create_private_file(&path).unwrap();
        file.write_all(b"fixture").unwrap();
        drop(file);
        assert!(private_file(&path));

        let sddl: Vec<u16> = std::ffi::OsStr::new("D:P(A;;FA;;;WD)").encode_wide()
            .chain(std::iter::once(0)).collect();
        let mut descriptor = std::ptr::null_mut();
        assert_ne!(unsafe { ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl.as_ptr(), SDDL_REVISION_1, &mut descriptor, std::ptr::null_mut()) }, 0);
        let name = wide_path(&path).unwrap();
        let changed = unsafe { SetFileSecurityW(name.as_ptr(), DACL_SECURITY_INFORMATION
            | PROTECTED_DACL_SECURITY_INFORMATION, descriptor) };
        unsafe { LocalFree(descriptor) };
        assert_ne!(changed, 0);
        assert!(!private_file(&path));
        std::fs::remove_file(&path).unwrap();
        std::fs::remove_dir(&root).unwrap();
    }
}
