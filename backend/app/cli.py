import argparse
import json
from pathlib import Path

from sqlalchemy import select

from app.db.models import (
    Category,
    Guide,
    GuideRevision,
    ResearchJob,
    ResearchJobStatus,
    User,
    UserRole,
)
from app.db.session import SessionLocal
from app.schemas.content import GuideDocument
from app.services.generation import run_generation_job
from app.services.guides import (
    create_guide,
    document_hash,
    publish_revision,
    revision_document,
    save_draft,
)

# The backend can be invoked from anywhere in the monorepo, so content is resolved
# against the package rather than the working directory.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = BACKEND_ROOT / "content" / "guides"

DEFAULT_CATEGORIES = [
    ("film", "Film", "Directors, canons, and the films everyone claims to have seen.", 10),
    ("series", "Series", "Prestige television, long-runners, and finale discourse.", 20),
    ("anime", "Anime", "Plot, character, ending, and fandom guides.", 30),
    ("gaming", "Gaming", "Games, communities, mechanics, and lore.", 40),
    ("music", "Music", "Artists, genres, scenes, and discographies.", 50),
    ("books", "Books", "Authors, canons, and the novels people carry unread.", 60),
    ("drink", "Drink", "Wine, coffee, spirits, and the vocabulary around them.", 70),
    ("food", "Food", "Cooking, restaurants, and the technique behind the plate.", 80),
    ("sport", "Sport", "Teams, athletes, rules, and the physical ones you cannot fake.", 90),
    ("design", "Design", "Architecture, objects, typefaces, and taste.", 100),
    ("style", "Style", "Clothes, watches, and the objects people wear as claims.", 105),
    ("job", "Jobs", "Professions, titles, and the ones you must not claim.", 110),
    ("tech", "Tech", "Tools, platforms, and engineering culture.", 120),
    ("general", "General", "Topics that do not fit a specialized guide template.", 200),
]


def system_user(db) -> User:
    user = db.scalar(select(User).where(User.clerk_user_id == "system:seed"))
    if user is None:
        user = User(
            clerk_user_id="system:seed",
            display_name="Content Seed",
            role=UserRole.ADMIN,
        )
        db.add(user)
        db.flush()
    return user


def seed() -> None:
    with SessionLocal() as db:
        for slug, title, description, sort_order in DEFAULT_CATEGORIES:
            category = db.scalar(select(Category).where(Category.slug == slug))
            if category is None:
                category = Category(slug=slug, title=title)
                db.add(category)
            category.title = title
            category.description = description
            category.sort_order = sort_order
            category.is_active = True
        db.commit()

        author = system_user(db)
        for path in sorted(CONTENT_DIR.glob("*.json")):
            document = GuideDocument.model_validate_json(path.read_text(encoding="utf-8"))
            guide = db.scalar(select(Guide).where(Guide.slug == document.slug))
            if guide is None:
                guide = create_guide(db, document, author)
                revision = db.scalar(
                    select(GuideRevision)
                    .where(GuideRevision.guide_id == guide.id)
                    .order_by(GuideRevision.revision_number.desc())
                    .limit(1)
                )
                if revision is None:
                    raise RuntimeError("New guide revision was not created")
            else:
                current = (
                    db.get(GuideRevision, guide.current_revision_id)
                    if guide.current_revision_id
                    else None
                )
                if current and current.content_hash == document_hash(document):
                    continue
                revision = save_draft(db, guide, document, author)
            publish_revision(db, guide, revision.id)
        db.commit()
    print("Seeded categories and published content guides.")


def set_role(clerk_user_id: str, role: UserRole) -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.clerk_user_id == clerk_user_id))
        if user is None:
            raise SystemExit("User not found. Sign in once before assigning a role.")
        user.role = role
        db.commit()
    print(f"Assigned {role.value} to {clerk_user_id}.")


def import_guide(path: Path, should_publish: bool) -> None:
    document = GuideDocument.model_validate_json(path.read_text(encoding="utf-8"))
    with SessionLocal() as db:
        author = system_user(db)
        guide = db.scalar(select(Guide).where(Guide.slug == document.slug))
        if guide is None:
            guide = create_guide(db, document, author)
            revision = db.scalar(
                select(GuideRevision)
                .where(GuideRevision.guide_id == guide.id)
                .order_by(GuideRevision.revision_number.desc())
                .limit(1)
            )
            if revision is None:
                raise RuntimeError("New guide revision was not created")
        else:
            revision = save_draft(db, guide, document, author)
        if should_publish:
            publish_revision(db, guide, revision.id)
        db.commit()
    print(f"Imported {document.slug}{' and published it' if should_publish else ''}.")


def export_guide(slug: str, output: Path) -> None:
    with SessionLocal() as db:
        guide = db.scalar(select(Guide).where(Guide.slug == slug))
        if guide is None:
            raise SystemExit("Guide not found.")
        revision = db.scalar(
            select(GuideRevision)
            .where(GuideRevision.guide_id == guide.id)
            .order_by(GuideRevision.revision_number.desc())
            .limit(1)
        )
        if revision is None:
            raise SystemExit("Guide has no revisions.")
        document = revision_document(revision)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(document.model_dump(mode="json", exclude_none=True), indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Exported {slug} to {output}.")


def work(limit: int) -> None:
    """Run queued generation jobs in this process. The API can also run them inline."""
    processed = 0
    with SessionLocal() as db:
        while processed < limit:
            job_id = db.scalar(
                select(ResearchJob.id)
                .where(ResearchJob.status == ResearchJobStatus.QUEUED)
                .order_by(ResearchJob.created_at)
                .limit(1)
            )
            if job_id is None:
                break
            job = run_generation_job(db, job_id)
            processed += 1
            detail = f" - {job.error_message}" if job.error_message else ""
            print(f"{job.topic}: {job.status.value}{detail}")
    print(f"Processed {processed} job(s).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Can I LARP It backend utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("seed", help="Seed categories and content/guides JSON files")

    role_parser = subparsers.add_parser("set-role", help="Assign an application role")
    role_parser.add_argument("clerk_user_id")
    role_parser.add_argument("role", choices=[role.value for role in UserRole])

    import_parser = subparsers.add_parser("import-guide", help="Import a guide JSON document")
    import_parser.add_argument("path", type=Path)
    import_parser.add_argument("--publish", action="store_true")

    export_parser = subparsers.add_parser("export-guide", help="Export the latest guide revision")
    export_parser.add_argument("slug")
    export_parser.add_argument("output", type=Path)

    work_parser = subparsers.add_parser("work", help="Run queued guide-generation jobs")
    work_parser.add_argument("--limit", type=int, default=1)

    args = parser.parse_args()
    if args.command == "seed":
        seed()
    elif args.command == "set-role":
        set_role(args.clerk_user_id, UserRole(args.role))
    elif args.command == "import-guide":
        import_guide(args.path, args.publish)
    elif args.command == "export-guide":
        export_guide(args.slug, args.output)
    elif args.command == "work":
        work(args.limit)


if __name__ == "__main__":
    main()
