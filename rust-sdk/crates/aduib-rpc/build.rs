fn main() -> Result<(), Box<dyn std::error::Error>> {
    use std::path::PathBuf;

    // Ensure protoc exists (use vendored binary).
    let protoc_path = protoc_bin_vendored::protoc_bin_path()?;
    std::env::set_var("PROTOC", protoc_path);

    // Prefer proto vendored inside the crate so `cargo publish` can build from
    // the packaged tarball (which cannot reference files outside the crate).
    // Fallback to the repo-root Python proto path for local development.
    let manifest_dir = PathBuf::from(std::env::var("CARGO_MANIFEST_DIR")?);

    let local_proto_dir = manifest_dir.join("proto");
    let local_proto_file = local_proto_dir.join("aduib_rpc.proto");

    let (proto_dir, proto_file) = if local_proto_file.exists() {
        (local_proto_dir, local_proto_file)
    } else {
        let repo_root = manifest_dir
            .parent() // crates/
            .and_then(|p| p.parent()) // rust-sdk/
            .and_then(|p| p.parent()) // repo root
            .ok_or("failed to resolve repo root from CARGO_MANIFEST_DIR")?
            .to_path_buf();

        let repo_proto_dir = repo_root.join("src").join("aduib_rpc").join("proto");
        let repo_proto_file = repo_proto_dir.join("aduib_rpc.proto");
        (repo_proto_dir, repo_proto_file)
    };

    println!("cargo:rerun-if-changed={}", proto_file.display());
    println!("cargo:rerun-if-changed={}", proto_dir.display());

    tonic_build::configure()
        .build_server(false)
        .compile_protos(&[proto_file], &[proto_dir])?;

    Ok(())
}
